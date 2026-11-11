"""Keep OpenCL failures and blocked driver calls outside the desktop process."""
import atexit
import multiprocessing as mp
import os
from pathlib import Path
import threading
import weakref
import numpy as np

_clients = weakref.WeakSet()


def _stop(process, connection):
    connection.close()
    if process.is_alive():
        process.terminate()
        process.join(timeout=2)
    if process.is_alive():
        process.kill()


def close_workers():
    for client in list(_clients):
        client.close()


atexit.register(close_workers)


def worker(connection, folder, cache):
    # Never unwind/destruct OpenCL objects after a driver failure: even cleanup
    # can block. The parent owns the timeout and Windows reclaims this process.
    try:
        import openvino as ov
        core = ov.Core()
        config = {'PERFORMANCE_HINT': 'LATENCY', 'NUM_STREAMS': ov.properties.streams.Num(1),
                  'PERFORMANCE_HINT_NUM_REQUESTS': 1,
                  'INFERENCE_PRECISION_HINT': ov.Type.f16, 'CACHE_DIR': cache}
        encoder = core.compile_model(str(Path(folder)/'encoder.xml'), 'GPU', config)
        network = core.read_model(str(Path(folder)/'decoder.xml'))
        shapes = {}
        for port in network.inputs:
            shape = port.get_partial_shape()
            shape[0] = 1
            shapes[port] = shape
        network.reshape(shapes)
        decoder = core.compile_model(network, 'GPU', config)
        devices = list(encoder.get_property('EXECUTION_DEVICES')) + list(decoder.get_property('EXECUTION_DEVICES'))
        if not all(d.startswith('GPU') for d in devices):
            raise RuntimeError('SAM neural networks did not compile for Intel GPU.')
        requests = {'encoder': encoder.create_infer_request(), 'decoder': decoder.create_infer_request()}
        networks = {'encoder': encoder, 'decoder': decoder}
        image_inputs = None
        connection.send(('ready', dict(name=core.get_property('GPU', 'FULL_DEVICE_NAME'),
            execution_devices=devices, active_device='intel-gpu', isolated_worker=True,
            streams=1, decoder_batch=1, precision='f16')))
        while True:
            kind, arrays = connection.recv()
            if kind == 'decoder':
                if arrays['image'] is not None:
                    image_inputs = arrays['image']
                sparse, dense = arrays['prompts']
                if dense.shape[-2:] == (1,1):
                    dense = np.ascontiguousarray(np.broadcast_to(dense,(1,dense.shape[1],64,64)))
                arrays = [image_inputs[0],image_inputs[1],sparse,dense,*image_inputs[2:]]
            request = requests[kind]
            result = request.infer(arrays, share_inputs=False, share_outputs=False)
            connection.send(('result', [result[p].copy() for p in networks[kind].outputs]))
    except EOFError:
        os._exit(0)
    except BaseException as error:
        try:
            connection.send(('error', str(error)))
        except BaseException:
            pass
        os._exit(86)


class GPUWorker:
    def __init__(self, folder, cache):
        context = mp.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=worker, args=(child,str(folder),str(cache)), daemon=True)
        self.lock = threading.Lock()
        self.closed = False
        self.process.start()
        child.close()
        self.finalizer = weakref.finalize(self, _stop, self.process, self.connection)
        _clients.add(self)
        try:
            self.info = self._receive(120, 'GPU model loading')
        except BaseException:
            self.close()
            raise

    def _receive(self, timeout, description):
        if not self.connection.poll(timeout):
            raise RuntimeError(f'{description} exceeded {timeout} seconds; GPU worker stopped.')
        kind, value = self.connection.recv()
        if kind == 'error':
            raise RuntimeError(value)
        return value

    def infer(self, kind, arrays):
        with self.lock:
            if self.closed:
                raise RuntimeError('GPU worker is closed.')
            try:
                self.connection.send((kind, arrays))
                return self._receive(30 if kind == 'encoder' else 20, 'GPU inference')
            except BaseException:
                self.close()
                raise

    def close(self):
        if not self.closed:
            self.closed = True
            self.finalizer()
