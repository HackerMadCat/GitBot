import os

from nltk.parse.stanford import StanfordParser, StanfordDependencyParser

stanford_dir = os.getenv("HOME") + "/NLP"
os.environ["STANFORD_DIR"] = stanford_dir
os.environ["STANFORD_MODELS"] = "{0}/stanford-postagger-full/models:{0}/stanford-ner/classifiers".format(stanford_dir)
os.environ[
    "CLASSPATH"] = "{0}/stanford-postagger-full/stanford-postagger.jar:{0}/stanford-ner/stanford-ner.jar:{0}/stanford-parser-full/stanford-parser.jar:{0}/stanford-parser-full/stanford-parser-3.5.2-models.jar".format(
        stanford_dir)

sp = StanfordParser(model_path="edu/stanford/nlp/models/lexparser/englishPCFG.ser.gz")
sdp = StanfordDependencyParser(model_path="edu/stanford/nlp/models/lexparser/englishPCFG.ser.gz")

phrase_level = {
    "ADJP", "ADVP", "CONJR", "FRAG", "INTJ", "LST", "NAC", "NP", "NX", "PP", "PRN", "PRT", "QP", "RRC", "UCP", "VP",
    "WHADJP", "WHAVP", "WHNP", "WHPP", "X"
}

word_level = {
    "CC", "CD", "DT", "EX", "FW", "IN", "JJ", "JJR", "JJS", "LS", "MD", "NN", "NNS", "NNP", "NNPS", "PDT", "POS", "PRP",
    "PRP$", "RB", "RBR", "RBS", "RP", "SYM", "TO", "UH", "VB", "VBD", "VBG", "VBP", "VBZ", "WDT", "WP", "WP$", "WRB"
}

conjunction_level = {"CC", ","}


def _subtrees(tree, labels: list) -> list:
    return [node for node in tree if not isinstance(node, str) and node.label() in labels]


def _trees(tree, labels: list) -> list:
    trees = [t for node in tree if not isinstance(node, str) for t in _trees(node, labels)]
    return _subtrees(tree, labels) + trees


def _parse_collocations(tree) -> list:
    nps = [[]]
    for node in tree:
        label = node.label()
        if label in conjunction_level:
            nps.append([])
        elif label in word_level:
            nps[-1].append(node[0])
    sdp_trees = [next(sdp.raw_parse(" ".join(words))) for words in nps if len(words) > 0]
    collocations = []
    for sdp_tree in sdp_trees:
        subject = {"NN": None, "JJ": []}
        for i, node in sdp_tree.nodes.items():
            if node["word"] is None: continue
            if node["head"] == 0:
                subject["NN"] = node["word"]
            else:
                subject["JJ"].append(node["word"])
        collocations.append(subject)
    return collocations


def _parse_collocation(collocation: list) -> dict:
    if len(collocation) == 1: return {"NN": collocation[0], "JJ": []}
    np = {"NN": None, "JJ": []}
    for i, node in next(sdp.raw_parse(" ".join(collocation))).nodes.items():
        if node["word"] is None: continue
        if node["head"] == 0:
            np["NN"] = node["word"]
        else:
            np["JJ"].append(node["word"])
    return np


def _parse_pp(tree) -> (list, list):
    result = []
    rpp = []
    for pp in _subtrees(tree, ["PP"]):
        if len(_subtrees(pp, ["PP"])) != 0:
            (_pp, _rpp) = _parse_pp(pp)
            for rp in _rpp:
                rp["DEPTH"] -= 1
                if rp["DEPTH"] <= 0:
                    del rp["DEPTH"]
                    result.append(rp)
                else:
                    rpp.append(rp)
            result.extend(_pp)
        _in = [_in[0] for _in in _subtrees(pp, ["IN"])]
        if len(_in) > 0:
            (_np, _rpp) = _parse_np(pp)
            for rp in _rpp:
                rp["DEPTH"] -= 1
                if rp["DEPTH"] <= 0:
                    del rp["DEPTH"]
                    result.append(rp)
                else:
                    rpp.append(rp)
            result.extend([{"IN": _in[0], "NP": _np}])
    return result, rpp


def _parse_np(tree) -> (list, list):
    result = []
    rpp = []
    for np in _subtrees(tree, ["NP"]):
        collocations = [[]]
        for node in np:
            label = node.label()
            if label in conjunction_level:
                collocations.append([])
            elif label in word_level:
                collocations[-1].append(node)
        nps = []
        pps = []
        for collocation in collocations:
            if len(collocation) == 0: continue
            _in = []
            _collocation = []
            for node in collocation:
                if node.label() == "POS":
                    _in.append(node[0])
                else:
                    _collocation.append(node[0])
            if len(_in) > 0:
                rpp.append({"IN": _in[0], "NP": [_parse_collocation(_collocation)], "DEPTH": 2})
            else:
                nps.append(_parse_collocation(_collocation))
        (_np, _rpp) = _parse_np(np)
        for rp in _rpp:
            rp["DEPTH"] -= 1
            if rp["DEPTH"] <= 0:
                del rp["DEPTH"]
                pps.append(rp)
            else:
                rpp.append(rp)
        (_pp, _rpp) = _parse_pp(np)
        for rp in _rpp:
            rp["DEPTH"] -= 1
            if rp["DEPTH"] <= 0:
                del rp["DEPTH"]
                pps.append(rp)
            else:
                rpp.append(rp)
        nps.extend(_np)
        pps.extend(_pp)
        if len(pps) == 0: result.extend(nps)
        else: result.append({"NP": nps, "PP": pps})
    return result, rpp


def _parse_sentence(tree) -> dict:
    sentence = {"NP": [], "VP": []}
    for np in _subtrees(tree, ["NP"]):
        sentence["NP"].extend(_parse_np(np)[0])
    for vp in _trees(tree, ["VP"]):
        for act in [vb[0] for vb in _subtrees(vp, ["VB", "VBD", "VBG", "VBN", "VBP", "VBZ"])]:
            vps = {"VB": act, "NP": [], "PP": []}
            (_np, _rpp) = _parse_np(vp)
            for rp in _rpp:
                if rp["DEPTH"] == 1: del rp["DEPTH"]
                vps["PP"].append(rp)
            (_pp, _rpp) = _parse_pp(vp)
            for rp in _rpp:
                if rp["DEPTH"] == 1: del rp["DEPTH"]
                vps["PP"].append(rp)
            vps["NP"].extend(_np)
            vps["PP"].extend(_pp)
            sentence["VP"].append(vps)
    return sentence


def parse(string: str) -> dict:
    if len(string.split()) == 0: return None
    sp_tree = next(sp.raw_parse(string))[0]
    if sp_tree.label() in ["NP", "FRAG"]:
        string = "show " + string
        sp_tree = next(sp.raw_parse(string))[0]
    print(sp_tree)
    return _parse_sentence(sp_tree) if sp_tree.label() == "S" else None


def tree(root: dict, shift=0) -> str:
    result = ["{\n"]
    for i, (key, col) in enumerate(sorted(root.items())):
        result.append("\t" * shift)
        result.append("'" + str(key) + "': ")
        if key in {"NN", "JJ", "VB", "IN"} or len(col) == 0:
            result.append(str(col))
        else:
            result.append("[")
            for j, value in enumerate(col):
                if isinstance(value, dict): result.append(tree(value, shift + 1))
                else: result.append(str(value))
                if j < len(col) - 1: result.append(", ")
            result.append("]")
        if i < len(root) - 1: result.append(",\n")
        else: result.append("\n")
    result.append("\t" * shift)
    result.append("}")
    return "".join(result)