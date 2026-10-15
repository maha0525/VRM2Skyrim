"""Check the dependencies loaded by this interpreter, including native modules."""
import importlib
import logging
import sys

LOG = logging.getLogger(__name__)
LZ4_PROBE = bytes.fromhex(
    '04224d1868401400000000000000a31400008056524d32536b7972696d204c5a342070726f626500000000')


def dependency_checks():
    checks = {'python': sys.version_info[:2] in ((3, 11), (3, 12))}
    if not checks['python']:
        LOG.error('Unsupported Python %s at %s; use Python 3.11/3.12 and Setup.cmd',
                  sys.version.split()[0], sys.executable)
    for name, module in (('numpy', 'numpy'), ('scipy', 'scipy'), ('PIL', 'PIL.Image'), ('lz4', 'lz4.frame')):
        try:
            loaded = importlib.import_module(module)
            if name == 'lz4' and loaded.decompress(LZ4_PROBE) != b'VRM2Skyrim LZ4 probe':
                raise ValueError('LZ4 decompression returned unexpected data')
        except Exception as error:
            checks[name] = False
            LOG.error('Dependency %s failed in %s: %s: %s. Run Setup.cmd to repair the project environment.',
                      module, sys.executable, type(error).__name__, error)
        else:
            checks[name] = True
            LOG.debug('Dependency %s ready: %s', module, getattr(loaded, '__file__', '<unknown>'))
    return checks


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    logging.info('Checking Python %s at %s', sys.version.split()[0], sys.executable)
    ready = all(dependency_checks().values())
    if ready:
        logging.info('Python dependencies ready, including LZ4 frame decompression')
    raise SystemExit(0 if ready else 1)
