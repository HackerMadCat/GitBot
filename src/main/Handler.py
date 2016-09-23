from copy import deepcopy
from github import GithubException

from main.types.Node import *
from src.main.types.Function import WFunction, NullFunction, Function
from src.main.types.Object import Object, LabeledObject
from src.main.types.Object import Null
from src import IO
from src.main import Simplifier
from src.main import Tables
from src.main.nlp import Corrector
from src.main.types import Types
from src.main.Connector import Connector, NotAutorisedUserException
from src.main.Utils import difference


class Handler:
    def __init__(self, bot_nick="Bot", default_nick="User", max_nick_len=20):
        self._connect = False
        self._connector = Connector()
        self._storeds = Tables.create_storeds_map()
        self._builders = Tables.create_builders_map(lambda: self._connector, lambda _type: self._storeds[_type])
        self._functions = Tables.create_functions_map(lambda: self)
        self._type_builders = Tables.create_type_builders_mpa(lambda: self._connector)
        self._bot_nick = bot_nick
        self._nick = default_nick
        self._default_nick = default_nick
        self._max_nick_len = max_nick_len

    def start(self):
        self._connect = True
        self._print("hello")
        while self._connect: self._handle()

    def stop(self):
        self._connect = False

    @staticmethod
    def format_nick(nick: str, max_len: int) -> str:
        return nick[max_len - 3] + "..." if len(nick) > max_len else " " * (max_len - len(nick)) + nick

    def _print(self, obj):
        for string in str(obj).split("\n"):
            if string == "": continue
            IO.writeln(self.format_nick(self._bot_nick, self._max_nick_len) + "  ::  " + string)

    def _read(self) -> str:
        return IO.readln(self.format_nick(self._nick, self._max_nick_len) + "  ::  ")

    def _hide_read(self) -> str:
        return IO.readln(self.format_nick("password", self._max_nick_len) + "  ::  ")
        # return IO.hreadln(self.format_nick(self._nick, self._max_nick_len) + "  ::  ")  # not work in pycharm console

    def _custom_read(self, prompt: str):
        return IO.readln(self.format_nick(prompt, self._max_nick_len) + "  ::  ")

    def _start_build(self, root: Root):
        if root is None: return
        for vp in root.vps:
            if len(vp.nps) == 0:
                for vb in vp.vbs:
                    vb = Simplifier.simplify_word(vb)
                    if vb not in self._functions: continue
                    self._functions[vb](Null())
            else:
                for node in vp.nps:
                    args = self._build(node, [])
                    for vb in vp.vbs:
                        vb = Simplifier.simplify_word(vb.text)
                        if vb not in self._functions: continue
                        for arg in args: self._functions[vb](arg)

    def _handle(self):
        data = self._read()
        root = Corrector.parse(data)
        IO.debug(root)
        try:
            self._start_build(root)
        except GithubException as ex:
            if ex.status == 403:
                self._print(ex.data["message"])
            else:
                raise ex

    def _execute(self, foo: Function, args: list):
        try:
            data = foo.run(*[arg.object for arg in args])
            if data is None:
                self._print("{} not found".format(str(foo.result).title()))
                return Null()
            else:
                return Object.create(foo.result, data)
        except GithubException as ex:
            if ex.status == 404:
                self._print("{} not found".format(str(foo.result).title()))
            else:
                raise ex
        except NotAutorisedUserException as _:
            self._print("I don't know who are you")
        return Null()

    def _get_relevant_shells(self, noun: str, adjectives: list) -> list:
        relevant_shells = []
        set_adjectives = set(adjectives)
        if noun in self._builders:
            shells = self._builders[noun]
            for shell in shells:
                set_shell_adjectives = set(shell["JJ"])
                conjunction = set_shell_adjectives & set_adjectives
                if len(conjunction) == len(set_shell_adjectives): relevant_shells.append(shell)
        return relevant_shells

    def _get_relevant_shell(self, noun: str, adjectives: list) -> dict:
        relevant_shells = self._get_relevant_shells(noun, adjectives)
        if len(relevant_shells) == 0: return None
        min_shell = relevant_shells[0]
        min_dist = abs(len(adjectives) - len(min_shell["JJ"]))
        for i, shell in enumerate(relevant_shells):
            if i == 0: continue
            distance = abs(len(adjectives) - len(shell["JJ"]))
            if distance < min_dist:
                min_dist = distance
                min_shell = shell
        return min_shell

    @staticmethod
    def _get_arguments(arguments: list, holes: list):
        arguments = list(deepcopy(arguments))
        relevant_arguments = []
        mass = 0
        primitives = False
        idle = False
        fine = 1
        while not (idle and primitives) and len(holes) > 0 and len(arguments) > 0:
            primitives = True
            idle = True
            for i, argument in enumerate(arguments):
                if not argument.type.isprimitive(): primitives = False
                if argument.type == holes[0]:
                    del holes[0]
                    del arguments[i]
                    relevant_arguments.append(argument)
                    mass += (i + 1) * fine
                    idle = False
                    break
            if idle:
                for argument in arguments: argument.simplify()
                fine += 4
            IO.debug("primitives = {}", primitives)
            IO.debug("idle = {}", idle)
            IO.debug("holes = {}", holes)
            IO.debug("arguments = {}", arguments)
            IO.debug("---------------------------")
        return relevant_arguments, mass

    def _get_relevant_function(self, noun: str, adjectives: list, functions: list, arguments: list) -> WFunction:
        relevant_function = NullFunction()
        for function in functions:
            holes = list(deepcopy(function.args))
            relevant_arguments, mass = self._get_arguments(arguments, holes)
            if noun in self._type_builders and len(holes) == 1 and len(function.args) == 1:
                temp_function = self._type_builders[noun]
                if holes == list(temp_function.args): function = temp_function
            pair = self._get_arguments(reversed([Object.valueOf(jj) for jj in adjectives]), holes)
            relevant_arguments.extend(pair[0])
            mass += pair[1] - 2 * len(function.args)
            IO.debug("function = {}", function)
            IO.debug("relevant_arguments = {}", relevant_arguments)
            IO.debug("relevant_function = {}", relevant_function)
            IO.debug("mass = {}", mass)
            IO.debug("+++++++++++++++++++++++++++")
            if len(holes) == 0 and relevant_function.mass > mass:
                relevant_function = WFunction(mass, relevant_arguments, function)
        return relevant_function

    def _build(self, node: NounPhrase, args: list) -> list:
        if isinstance(node, LeafNounPhrase):
            string, noun, adjectives, types = Simplifier.simplify(node)
            if len(types) == 1:
                type_name = str(types[0])
                if type_name in self._builders and noun not in self._builders:
                    adjectives.remove(type_name)
                    adjectives.append(string)
                    noun = type_name
            constructed_object = None
            function = NullFunction()
            shell = self._get_relevant_shell(noun, adjectives)
            if shell is not None:
                adjectives = difference(adjectives, shell["JJ"])
                function = self._get_relevant_function(noun, adjectives, shell["F"], args)
                if not isinstance(function, NullFunction):
                    constructed_object = self._execute(function, function.relevant_args)
            if constructed_object is None: constructed_object = Object.valueOf(string)
            IO.debug("relevant_function = {}", function)
            IO.debug("===========================")
            return [constructed_object]
        else:
            _args = [LabeledObject(pp.pretext, arg) for pp in node.pps for np in pp.nps for arg in self._build(np, [])]
            return [arg for np in node.nps for arg in self._build(np, args + _args)]

    def show(self, obj: Object):
        if obj.type == Types.String():
            word = Simplifier.simplify_word(str(obj.object))
            if word in self._functions: self._functions[word](obj)
        else:
            string = str(obj)
            if not (string + ' ').isspace(): self._print(string)

    def store(self, obj: Object):
        if obj.type == Types.String() and obj.object == "me":
            try:
                self._storeds[Types.User()] = self._connector.user()
                self._print("I remember it")
            except NotAutorisedUserException as _:
                self._print("I don't know who are you")
        elif obj.type in self._storeds:
            self._storeds[obj.type] = obj.object
            self._print("I remember it")
        else:
            self._print("I can not remember " + str(obj.type))

    def log(self, obj: Object):
        if obj.type != Types.String(): return
        value = obj.object
        if value == "out":
            self.logout(obj)
        elif value == "in":
            self.login(obj)

    def logout(self, _: Object):
        if self._connector.authorised():
            self._connector.logout()
            self._nick = self._default_nick

    def login(self, _: Object):
        if self._connector.authorised():
            self._print("logout before you login again")
        else:
            self._print("enter your login for github")
            login = self._custom_read("login")
            self._print("enter password")
            password = self._hide_read()
            if not self._connector.isauthorised(login, password):
                self._nick = self._default_nick
                self._print("incorrect login or password")
            else:
                self._nick = self._connector.authorised()

    def hello(self, _: Object):
        self._print("=)")

    def bye(self, _: Object):
        self._print("bye")
        self.stop()
