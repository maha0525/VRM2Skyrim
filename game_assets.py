"""Resolve official archive assets or the user's deployed modded appearance."""
import logging
from pathlib import Path
import shutil

from bsa import BSA

LOG = logging.getLogger(__name__)


class GameAssets:
    def __init__(self, data, plugins, output, installed=False):
        self.data, self.output = Path(data), Path(output)
        self.installed = installed
        names = [f'Skyrim - Meshes{i}.bsa' for i in range(2)] + [f'Skyrim - Textures{i}.bsa' for i in range(9)]
        for plugin in plugins:
            stem = Path(plugin).stem
            names += [stem + '.bsa', stem + ' - Textures.bsa']
        self.paths = list(dict.fromkeys(self.data / n for n in names if (self.data / n).is_file()))
        self.archives = {}

    def extract(self, name, kind='meshes'):
        name = name.lower().replace('\\', '/')
        if not name.startswith(kind + '/'):
            name = kind + '/' + name
        if ':' in name or '..' in Path(name).parts or name.startswith('/'):
            raise ValueError('Unsafe game asset path')
        dest = self.output / name
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        loose = self.data / name
        if self.installed and loose.is_file():
            shutil.copyfile(loose, dest)
            LOG.debug('Asset from deployed loose file: %s', name)
            return dest
        for path in reversed(self.paths):
            if kind == 'meshes' and 'textures' in path.name.lower():
                continue
            if kind == 'textures' and 'meshes' in path.name.lower():
                continue
            if path not in self.archives:
                self.archives[path] = BSA(path)
            archive = self.archives[path]
            if name in archive.entries:
                archive.extract(name, dest)
                LOG.debug('Asset from %s: %s', path.name, name)
                return dest
        raise FileNotFoundError(f'Game asset missing from selected reference profile: {name}')
