def test_skill_layout_smoke():
    import json
    from pathlib import Path
    root = Path(__file__).parents[2]
    assert json.loads((root / "metadata.json").read_text(encoding="utf-8"))["name"] == "website-exploration"
