from copy import deepcopy

from github import GithubException
from src import IO
from src.main import Simplifier
from src.main import Tables
from src.main.GitConnector import Connector
from src.main.nlp import Corrector


class GitHandler:
    def __init__(self, bot_nick="Bot", default_nick="User", max_nick_len=20):
        self._connect = False
        self._connector = Connector()
        self._storeds = Tables.create_storeds_map()
        self._builders = Tables.create_builders_map((lambda: self._connector), (lambda _type: self._storeds[_type]))
        self._functions = Tables.create_functions_map((lambda: self))
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
        IO.writeln(self.format_nick(self._bot_nick, self._max_nick_len) + "  ::  " + str(obj))

    def _read(self) -> str:
        return IO.readln(self.format_nick(self._nick, self._max_nick_len) + "  ::  ")

    def _hide_read(self) -> str:
        # return IO.readln(self.format_nick(self._nick, self._max_nick_len) + "  ::  ")
        return IO.hreadln(self.format_nick(self._nick, self._max_nick_len) + "  ::  ")  # not work in pycharm console

    def _handle(self):
        data = self._read()
        parse = Corrector.parse(data)

        # IO.writeln(Corrector.tree(parse))

        if parse is None: return
        for vp in parse["VP"]:
            if len(vp["NP"]) == 0:
                for vb in vp["VB"]:
                    vb = Simplifier.simplify_word(vb)
                    if vb not in self._functions: continue
                    self._functions[vb]({"T": "none", "O": None})
            else:
                for node in vp["NP"]:
                    args = self._build(node, [])
                    for vb in vp["VB"]:
                        vb = Simplifier.simplify_word(vb)
                        if vb not in self._functions: continue
                        for arg in args: self._functions[vb](arg)

    @staticmethod
    def distance(list1: list, list2: list) -> float:
        return abs(len(list1) - len(list2))

    def _execute(self, foo: dict, args: list):
        try:
            return {"T": foo["T"], "O": foo["B"](*[arg["O"] for arg in args])}
        except GithubException as ex:
            if ex.status == 404:
                self._print("{} not found".format(" ".join(foo["T"]).title()))
            elif ex.status == 403:
                self._print(ex.data["message"])
            else:
                raise ex
        return {"T": foo["T"], "O": None}

    def _build(self, node: dict, args: list) -> list:
        if "NN" in node:
            string = node["NN"]
            noun = Simplifier.simplify_word(string)
            adjectives = Simplifier.simplify_exp(node["JJ"])
            relevant_shells = []
            if noun in self._builders:
                shells = self._builders[noun]
                for shell in shells:
                    set_shell_adjectives = set(shell["JJ"])
                    conjunction = set_shell_adjectives & set(adjectives)
                    if len(conjunction) == len(set_shell_adjectives):
                        relevant_shells.append(shell)
            constructed_object = None
            relevant_function = {"M": float("Inf")}
            if len(relevant_shells) != 0:
                min_shell = relevant_shells[0]
                min_dist = self.distance(adjectives, min_shell["JJ"])
                for i, shell in enumerate(relevant_shells):
                    if i == 0: continue
                    distance = self.distance(adjectives, shell["JJ"])
                    if distance < min_dist:
                        min_dist = distance
                        min_shell = shell
                shell = min_shell
                for function in shell["F"]:
                    holes = deepcopy(function["A"])
                    relevant_args = []
                    _args = deepcopy(args)
                    all_primitive = False
                    idle = False
                    mass = 0
                    fine = 1
                    while not (idle and all_primitive) and len(holes) > 0 and len(_args) > 0:
                        all_primitive = True
                        idle = True
                        for i, arg in enumerate(_args):
                            if arg["T"][0] not in Tables.primitive_types: all_primitive = False
                            if arg["T"] == holes[0]:
                                del holes[0]
                                del _args[i]
                                relevant_args.append(arg)
                                mass += (i + 1) * fine
                                idle = False
                                break
                        if idle:
                            _args = [Simplifier.simplify_object(arg) for arg in _args]
                            fine += 4
                    _args = [Simplifier.get_object(jj) for jj in adjectives]
                    idle = False
                    fine = 1
                    while not idle and len(holes) > 0 and len(_args) > 0:
                        idle = True
                        for i, arg in reversed(list(enumerate(_args))):
                            if arg["T"] == holes[0]:
                                del holes[0]
                                relevant_args.append(arg)
                                mass += (i + 1) * fine
                                idle = False
                                break
                        if idle: fine += 4
                    if len(holes) > 0: mass = float("Inf")
                    if relevant_function["M"] > mass:
                        relevant_function = {"M": mass, "A": relevant_args, "F": function}
            if relevant_function["M"] < float("Inf"):
                constructed_object = self._execute(relevant_function["F"], relevant_function["A"])
            if constructed_object is None:
                types = Simplifier.extract_types(adjectives)
                obj = Simplifier.get_object(string)
                if len(types) == 1 and types[0] in self._builders:
                    shells = self._builders[types[0]]
                    functions = []
                    for shell in shells:
                        if len(shell["JJ"]) == 0:
                            functions = shell["F"]
                            break
                    for function in functions:
                        _args = function["A"]
                        if len(_args) == 1 and _args[0] == obj["T"]:
                            constructed_object = self._execute(function, [obj])
                            break
                if constructed_object is None:
                    constructed_object = {"T": obj["T"], "O": obj["O"]}
            return [constructed_object]
        else:
            _args = [{**{"IN": pp["IN"]}, **arg} for pp in node["PP"] for np in pp["NP"] for arg in self._build(np, [])]
            return [arg for np in node["NP"] for arg in self._build(np, args + _args)]

    @staticmethod
    def string(obj, _type="") -> str:
        if _type == "user":
            if obj is None: return "User ───║───"
            login = GitHandler.string(obj.login, "login")
            name = GitHandler.string(obj.name, "name")
            email = GitHandler.string(obj.email, "email")
            return "{}({}) {}".format(login, name, email)
        elif _type == "repo":
            if obj is None: return "Repo ───║───"
            login = GitHandler.string(obj.owner.login, "login")
            name = GitHandler.string(obj.name, "name")
            _id = GitHandler.string(obj.id, "id")
            return "{}'s repo {}({})".format(login, name, _id)
        elif _type == "gist":
            if obj is None: return "Gist ───║───"
            login = GitHandler.string(obj.owner.login, "login")
            _id = GitHandler.string(obj.id, "id")
            return "{}'s gist id:{}".format(login, _id)
        elif _type == "name":
            if obj is None: return "───║───"
            return str(obj)
        elif _type == "email":
            if obj is None: return "<───║───>"
            return '<' + str(obj) + '>'
        elif _type == "str":
            if obj is None: return '"───║───"'
            return '"' + str(obj) + '"'
        else:
            if obj is None: return "───║───"
            return str(obj)

    def show(self, obj: dict):
        word = Simplifier.simplify_word(str(obj["O"]))
        if obj["T"] == ["str"] and Simplifier.simplify_word(obj["O"]) in self._functions:
            self._functions[word]({"T": obj["T"], "O": obj["O"]})
        else:
            _type = obj["T"]
            if _type[0] == "list":
                for elem in obj["O"]: self._print(self.string(elem, _type[1]))
            else:
                self._print(self.string(obj["O"], _type[0]))

    def store(self, obj: dict):
        _type = obj["T"]
        if _type[0] in self._storeds:
            self._storeds[_type[0]] = obj
            self._print("I remember it")
        else:
            self._print("I don't know who are you")

    def log(self, obj: dict):
        if obj["T"] != "str": return
        value = obj["O"]
        if value == "out":
            self.logout(obj)
        elif value == "in":
            self.login(obj)

    def login(self, _: dict):
        if self._connector.authorised():
            self._print("you need to unlogin before you login again")
        else:
            self._print("login:")
            login = self._read()
            self._print("password:")
            password = self._hide_read()
            if not self._connector.authorise(login, password):
                self._nick = self._default_nick
                self._print("Incorrect input: login or password")
            else:
                self._nick = self._connector.authorised()

    def logout(self, _: dict):
        if self._connector.authorised():
            self._connector.logout()
            self._nick = self._default_nick

    def hello(self, _: dict):
        self._print("=)")

    def bye(self, _: dict):
        self._print("bye")
        self.stop()
