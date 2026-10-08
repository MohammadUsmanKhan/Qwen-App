from app.generators.doc_spec import HeadingBlock, ListBlock, ListItem, ParagraphBlock, QuoteBlock, TableBlock
from app.generators.markdown_blocks import markdown_to_blocks


def test_mixed_markdown() -> None:
    blocks = markdown_to_blocks(
        "# Title\n\npara one\n\n## Sub\n- a\n- b\n    - deep\n\n> quote\n> more\n\n"
        "| x | y |\n| :-- | --: |\n| 1 | 2 |\n\n#### four\n"
    )
    kinds = [type(b).__name__ for b in blocks]
    assert kinds == [
        "HeadingBlock",
        "ParagraphBlock",
        "HeadingBlock",
        "ListBlock",
        "QuoteBlock",
        "TableBlock",
        "HeadingBlock",
    ]
    assert isinstance(blocks[0], HeadingBlock) and blocks[0].level == 1
    assert isinstance(blocks[1], ParagraphBlock) and blocks[1].text == "para one"
    lst = blocks[3]
    assert isinstance(lst, ListBlock)
    assert [(i.text, i.level) for i in lst.items if isinstance(i, ListItem)] == [("a", 0), ("b", 0), ("deep", 2)]
    assert isinstance(blocks[4], QuoteBlock) and blocks[4].text == "quote more"
    table = blocks[5]
    assert isinstance(table, TableBlock) and table.columns == ["x", "y"] and table.rows == [["1", "2"]]
    assert isinstance(blocks[6], HeadingBlock) and blocks[6].level == 3  # capped at 3


def test_numbered_list_and_pagebreak() -> None:
    blocks = markdown_to_blocks("1. one\n2) two\n\n<!-- pagebreak -->\nafter")
    assert isinstance(blocks[0], ListBlock) and blocks[0].style == "number"
    assert type(blocks[1]).__name__ == "PageBreakBlock"
    assert isinstance(blocks[2], ParagraphBlock)
