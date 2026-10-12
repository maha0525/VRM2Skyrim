"""Small strict Skyrim-PEX reader/executor for this runtime's isolated tests.

Binary layout/opcodes: Orvid/Caprica v0.3.0 Caprica/pex readers. Native calls use
an in-memory actor only. This does not simulate the game's outfit AI/rendering.
"""
import struct

from equipment_runtime import pex_strings


class PexVM:
    def __init__(self, data, actor, bindings):
        _, _, self.offset, raw = pex_strings(data)
        self.data, self.strings, self.actor = data, [s.decode() for s in raw], actor
        self.variables, self.functions, self.properties = {}, {}, {}
        if self.read('B'):
            self.read('Q')
            for _ in range(self.read('H')):
                self.read('HHHB')
                line_count = self.read('H')
                self.offset += 2*line_count
        for _ in range(self.read('H')):
            self.read('HB')
        assert self.read('H') == 1
        self.name = self.string()
        self.read('I')
        self.parent = self.string()
        self.string()
        self.read('I')
        self.string()
        for _ in range(self.read('H')):
            name = self.string().lower()
            self.string()
            self.read('I')
            self.variables[name] = self.value()[1]
        for _ in range(self.read('H')):
            name = self.string()
            self.string()
            self.string()
            self.read('I')
            assert self.read('B') & 4
            variable = self.string().lower()
            self.properties[name] = variable
            self.variables[variable] = bindings[name]
        for _ in range(self.read('H')):
            self.string()
            for _ in range(self.read('H')):
                name = self.string().lower()
                self.string()
                self.string()
                self.read('IB')
                parameters, types = [], {}
                for _ in range(self.read('H')):
                    parameter = self.string().lower()
                    parameters.append(parameter)
                    types[parameter] = self.string().lower()
                for _ in range(self.read('H')):
                    local = self.string().lower()
                    types[local] = self.string().lower()
                code = []
                for _ in range(self.read('H')):
                    op = self.read('B')
                    counts = {1: 3, 5: 3, 10: 2, 13: 2, 14: 2, 15: 3, 16: 3, 18: 3,
                              20: 1, 22: 2, 23: 3, 25: 3, 26: 1, 27: 3}
                    args = [self.value() for _ in range(counts[op])]
                    extra = []
                    if op in (23, 25):
                        tag, count = self.value()
                        assert tag == 3
                        extra = [self.value() for _ in range(count)]
                    code.append((op, args, extra))
                self.functions[name] = (parameters, types, code)
        assert self.offset == len(data), (self.offset, len(data))

    def read(self, fmt):
        values = struct.unpack_from('>'+fmt, self.data, self.offset)
        self.offset += struct.calcsize('>'+fmt)
        return values[0] if len(values) == 1 else values

    def string(self):
        return self.strings[self.read('H')]

    def value(self):
        tag = self.read('B')
        if tag == 0:
            return tag, None
        if tag in (1, 2):
            return tag, self.string()
        return tag, self.read({3: 'i', 4: 'f', 5: 'B'}[tag])

    def run(self, name, *arguments):
        parameters, types, code = self.functions[name.lower()]
        local = dict(zip(parameters, arguments))
        def get(value):
            tag, content = value
            if tag != 1:
                return content
            key = content.lower()
            if key == 'self':
                return self.actor
            return local.get(key, self.variables.get(key))
        def put(target, value):
            key = target[1].lower()
            if key in self.variables:
                self.variables[key] = value
            else:
                local[key] = value
        pc, steps = 0, 0
        while pc < len(code):
            steps += 1
            assert steps < 1000, 'PEX loop did not terminate'
            op, args, extra = code[pc]
            advance = 1
            if op == 13:
                put(args[0], get(args[1]))
            elif op == 14:
                value = get(args[1])
                kind = types[args[0][1].lower()]
                put(args[0], bool(value) if kind == 'bool' else str(value) if kind == 'string' else value)
            elif op in (1, 5, 15, 16, 18, 27):
                left, right = get(args[1]), get(args[2])
                put(args[0], {1: lambda: left+right, 5: lambda: left*right, 15: lambda: left == right, 16: lambda: left<right,
                              18: lambda: left>right, 27: lambda: str(left)+str(right)}[op]())
            elif op == 10:
                put(args[0], not get(args[1]))
            elif op == 20:
                advance = get(args[0])
            elif op == 22:
                if not get(args[0]):
                    advance = get(args[1])
            elif op == 26:
                return get(args[0])
            elif op == 25:
                assert args[0][1].lower() == 'debug' and args[1][1].lower() == 'trace'
                self.actor.logs.append(get(extra[0]))
                put(args[2], None)
            elif op == 23:
                method, target = args[0][1].lower(), get(args[1])
                values = [get(v) for v in extra]
                if target is self.actor:
                    result = self.run(method, *values) if method in self.functions else self.actor.call(method, values)
                elif method == 'getsize':
                    result = len(target)
                elif method == 'getat':
                    result = target[values[0]]
                elif method == 'hasform':
                    result = values[0] in target
                else:
                    raise AssertionError(method)
                put(args[2], result)
            pc += advance


class Actor:
    def __init__(self, inventory, teammate=False):
        self.inventory, self.teammate = dict(inventory), teammate
        self.worn, self.logs, self.events = set(), [], []
        self.skin, self.refreshes, self.registered = None, 0, False
        self.worn_slots = {}

    def call(self, name, values):
        if name == 'getactorbase':
            return self
        if name == 'getwornform':
            item = self.worn_slots.get(values[0])
            return item if item in self.worn else None
        if name == 'getskin':
            return self.skin
        if name == 'setskin':
            self.skin = values[0]
            return None
        if name == 'queueninodeupdate':
            self.refreshes += 1
            return None
        if name == 'registerforninodeupdate':
            self.registered = True
            return None
        if name == 'isplayerteammate':
            return self.teammate
        if name == 'getitemcount':
            return self.inventory.get(values[0], 0)
        if name == 'isequipped':
            return values[0] in self.worn
        if name == 'equipitem':
            assert values[1:] == [0, 1]
            self.worn.add(values[0])
            self.events.append(values[0])
            return None
        if name == 'unequipitem':
            assert values[1:] == [0, 1]
            self.worn.discard(values[0])
            return None
        raise AssertionError('Unexpected native mutation: '+name)

    def drain_events(self, vm):
        while self.events:
            vm.run('OnObjectEquipped', self.events.pop(0), None)
