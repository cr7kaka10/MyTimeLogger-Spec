from server.domain.flash_proofreading import validate_minimal_polish


def test_minimal_proofreading_returns_edits_and_protects_literals():
    text, code, edits = validate_minimal_polish("一个有一个", "一个又一个")
    assert (text, code, edits) == ("一个又一个", "polish_accepted", [{"source": "有", "replacement": "又", "kind": "replace"}])
    assert validate_minimal_polish("好烦烦啊", "好烦啊")[:2] == ("好烦啊", "polish_accepted")
    assert validate_minimal_polish("antigravity GPT-5.6 3", "antigravity GPT 3")[:2] == ("antigravity GPT-5.6 3", "polish_protected_literal")
    assert validate_minimal_polish("纯吐槽！", "纯吐槽！") == ("纯吐槽！", "polish_accepted", [])


def test_minimal_proofreading_rejects_large_rewrite_but_allows_short_fix():
    assert validate_minimal_polish("我今夭很烦", "我今天很烦")[:2] == ("我今天很烦", "polish_accepted")
    assert validate_minimal_polish("我今夭很烦烦啊", "我今夭很烦烦啊")[:2] == ("我今天很烦啊", "polish_accepted")
    assert validate_minimal_polish("大约半个小时左右", "大约半个小时左右")[:2] == ("大约半个小时", "polish_accepted")
    assert validate_minimal_polish("antigravity真是战犯，纯粹是卧底捣乱。", "antigravity浪费时间，像路边的狗。")[:2] == ("antigravity真是战犯，纯粹是卧底捣乱。", "polish_edit_budget")
