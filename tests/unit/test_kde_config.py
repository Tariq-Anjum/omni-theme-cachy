"""Unit tests for the central KDE/KConfig INI primitives (session 13).

``core.kde_config`` owns every section-safe edit of KDE INI-style text.
These tests pin the guarantees other sessions rely on: byte-preserving
edits outside the managed key, no duplicate sections, idempotency, and
survival of ``[$e]``-style key suffixes. All fixtures are inline text;
nothing touches the real user configuration.
"""

from __future__ import annotations

import pytest

from core.kde_config import parse_ini, remove_ini_key, set_ini_key


PROFILE_WITH_SECTION = (
    "[General]\n"
    "Command=/bin/zsh\n"
    "Name=ZSH\n"
    "\n"
    "[Appearance]\n"
    "ColorScheme=BreezeDark\n"
    "Opacity=1\n"
    "\n"
    "[Toolbar]\n"
    "ToolButtonStyle=IconOnly\n"
)


class TestParseIni:
    def test_groups_and_keys(self):
        entries = parse_ini(PROFILE_WITH_SECTION)
        assert entries[("General", "Command")] == "/bin/zsh"
        assert entries[("Appearance", "ColorScheme")] == "BreezeDark"
        assert entries[("Toolbar", "ToolButtonStyle")] == "IconOnly"

    def test_last_assignment_wins(self):
        text = "[A]\nKey=first\n[B]\nOther=1\n[A]\nKey=second\n"
        assert parse_ini(text)[("A", "Key")] == "second"

    def test_suffixed_keys_are_distinct_entries(self):
        text = "[A]\nColorScheme=plain\nColorScheme[$e]=expanded\nName[en_US]=Hello\n"
        entries = parse_ini(text)
        assert entries[("A", "ColorScheme")] == "plain"
        assert entries[("A", "ColorScheme[$e]")] == "expanded"
        assert entries[("A", "Name[en_US]")] == "Hello"

    def test_comments_and_blank_lines_ignored(self):
        text = "# top comment\n\n[A]\n# inside\nKey=v\n"
        assert parse_ini(text) == {("A", "Key"): "v"}


class TestSetExistingSection:
    def test_replaces_existing_key_in_place(self):
        new_text, previous, existed = set_ini_key(
            PROFILE_WITH_SECTION, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert previous == "BreezeDark"
        assert existed is True
        assert "ColorScheme=OmniTheme\n" in new_text
        assert "ColorScheme=BreezeDark" not in new_text

    def test_unrelated_keys_survive_byte_exact(self):
        new_text, _, _ = set_ini_key(
            PROFILE_WITH_SECTION, "Appearance", "ColorScheme", "OmniTheme"
        )
        for fragment in (
            "[General]\nCommand=/bin/zsh\nName=ZSH\n\n",
            "Opacity=1\n\n[Toolbar]\nToolButtonStyle=IconOnly\n",
        ):
            assert fragment in new_text

    def test_inserts_into_existing_section_before_next_header(self):
        text = "[Appearance]\nOpacity=1\n\n[Toolbar]\nToolButtonStyle=IconOnly\n"
        new_text, previous, existed = set_ini_key(
            text, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert (previous, existed) == (None, False)
        assert new_text == (
            "[Appearance]\nOpacity=1\nColorScheme=OmniTheme\n\n"
            "[Toolbar]\nToolButtonStyle=IconOnly\n"
        )

    def test_missing_section_appended_at_end(self):
        text = "[General]\nCommand=/bin/zsh\n"
        new_text, previous, existed = set_ini_key(
            text, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert (previous, existed) == (None, False)
        assert new_text == (
            "[General]\nCommand=/bin/zsh\n[Appearance]\nColorScheme=OmniTheme\n"
        )

    def test_missing_section_appended_without_trailing_newline(self):
        new_text, _, _ = set_ini_key("[General]\nCommand=/bin/zsh", "A", "K", "v")
        assert new_text == "[General]\nCommand=/bin/zsh\n[A]\nK=v\n"

    def test_empty_file(self):
        new_text, _, _ = set_ini_key("", "A", "K", "v")
        assert new_text == "[A]\nK=v\n"

    def test_empty_file_ending_in_newline(self):
        new_text, _, _ = set_ini_key("\n", "A", "K", "v")
        assert new_text == "\n[A]\nK=v\n"


class TestNoDuplicateSections:
    def test_repeated_application_is_idempotent(self):
        once, _, _ = set_ini_key(
            PROFILE_WITH_SECTION, "Appearance", "ColorScheme", "OmniTheme"
        )
        twice, previous, existed = set_ini_key(
            once, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert twice == once
        assert (previous, existed) == ("OmniTheme", True)

    def test_no_second_section_header_created(self):
        text = "[General]\nCommand=/bin/zsh\n"
        new_text, _, _ = set_ini_key(text, "Appearance", "ColorScheme", "OmniTheme")
        new_text, _, _ = set_ini_key(new_text, "Appearance", "ColorScheme", "OmniTheme")
        assert new_text.count("[Appearance]") == 1
        assert new_text.count("ColorScheme=") == 1

    def test_preexisting_duplicate_sections_key_updated_in_winning_block(self):
        text = (
            "[Appearance]\nColorScheme=First\n\n"
            "[Other]\nX=1\n\n"
            "[Appearance]\nColorScheme=Second\n"
        )
        new_text, previous, existed = set_ini_key(
            text, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert (previous, existed) == ("Second", True)
        assert "ColorScheme=First" in new_text  # earlier occurrence untouched
        assert "ColorScheme=Second" not in new_text
        assert "ColorScheme=OmniTheme" in new_text
        assert new_text.count("[Appearance]") == 2  # no third section

    def test_preexisting_duplicate_sections_key_inserted_into_last_block(self):
        text = "[Appearance]\nOpacity=1\n\n[Other]\nX=1\n\n[Appearance]\nOpacity=0.5\n"
        new_text, _, _ = set_ini_key(text, "Appearance", "ColorScheme", "OmniTheme")
        assert new_text.count("[Appearance]") == 2
        assert new_text.count("ColorScheme=") == 1
        first_block, second_block = new_text.split("[Appearance]")[1:]
        assert "ColorScheme" not in first_block
        assert "ColorScheme=OmniTheme" in second_block


class TestSuffixedKeys:
    def test_unrelated_suffixed_keys_survive_byte_exact(self):
        text = (
            "[General]\nName[$e]=ZSH\nName[en_US]=Hello\n\n"
            "[Appearance]\nColorScheme=BreezeDark\n"
        )
        new_text, _, _ = set_ini_key(
            text, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert "Name[$e]=ZSH\n" in new_text
        assert "Name[en_US]=Hello\n" in new_text

    def test_target_key_suffix_preserved_when_rewriting(self):
        text = "[Appearance]\nColorScheme[$e]=BreezeDark\n"
        new_text, previous, existed = set_ini_key(
            text, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert (previous, existed) == ("BreezeDark", True)
        assert new_text == "[Appearance]\nColorScheme[$e]=OmniTheme\n"

    def test_variant_found_in_later_block_reported_as_previous(self):
        text = "[Appearance]\nColorScheme=Plain\n\n[Appearance]\nColorScheme[$i]=Flag\n"
        new_text, previous, existed = set_ini_key(
            text, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert (previous, existed) == ("Flag", True)
        assert "ColorScheme=Plain" in new_text
        assert new_text.endswith("ColorScheme[$i]=OmniTheme\n")


class TestRemoveIniKey:
    def test_removes_key_keeps_header_and_siblings(self):
        new_text = remove_ini_key(PROFILE_WITH_SECTION, "Appearance", "ColorScheme")
        assert "[Appearance]" in new_text
        assert "Opacity=1" in new_text
        assert "ColorScheme" not in new_text
        assert "Command=/bin/zsh" in new_text

    def test_set_back_to_previous_restores_original_bytes(self):
        once, previous, existed = set_ini_key(
            PROFILE_WITH_SECTION, "Appearance", "ColorScheme", "OmniTheme"
        )
        assert (previous, existed) == ("BreezeDark", True)
        restored, _, _ = set_ini_key(once, "Appearance", "ColorScheme", previous)
        assert restored == PROFILE_WITH_SECTION

    def test_removes_suffixed_variants_too(self):
        text = "[Appearance]\nColorScheme[$e]=BreezeDark\nOpacity=1\n"
        new_text = remove_ini_key(text, "Appearance", "ColorScheme")
        assert new_text == "[Appearance]\nOpacity=1\n"

    def test_remove_across_duplicate_sections(self):
        text = "[Appearance]\nColorScheme=A\n\n[Appearance]\nColorScheme[$e]=B\n"
        new_text = remove_ini_key(text, "Appearance", "ColorScheme")
        assert new_text == "[Appearance]\n\n[Appearance]\n"

    def test_remove_missing_section_is_noop(self):
        assert remove_ini_key("[Other]\nX=1\n", "Appearance", "ColorScheme") == (
            "[Other]\nX=1\n"
        )


class TestFormatStability:
    def test_comments_and_blank_lines_survive_edit(self):
        text = (
            "# profile\n"
            "[Appearance]\n"
            "# the scheme\n"
            "ColorScheme=BreezeDark\n"
            "\n"
            "[Toolbar]\n"
            "ToolButtonStyle=IconOnly\n"
        )
        new_text, _, _ = set_ini_key(text, "Appearance", "ColorScheme", "OmniTheme")
        assert new_text == (
            "# profile\n"
            "[Appearance]\n"
            "# the scheme\n"
            "ColorScheme=OmniTheme\n"
            "\n"
            "[Toolbar]\n"
            "ToolButtonStyle=IconOnly\n"
        )

    def test_insertion_preserves_trailing_blank_line_of_block(self):
        text = "[Appearance]\nOpacity=1\n\n\n[Toolbar]\nX=1\n"
        new_text, _, _ = set_ini_key(text, "Appearance", "ColorScheme", "OmniTheme")
        assert new_text == "[Appearance]\nOpacity=1\nColorScheme=OmniTheme\n\n\n[Toolbar]\nX=1\n"

    def test_key_with_spaces_around_equals_is_normalised_in_place(self):
        text = "[Appearance]\nColorScheme = BreezeDark\n"
        new_text, _, _ = set_ini_key(text, "Appearance", "ColorScheme", "OmniTheme")
        assert new_text == "[Appearance]\nColorScheme=OmniTheme\n"


@pytest.mark.parametrize("value", ["OmniTheme", "A B C", "r,g,b", ""])
def test_values_round_trip(value):
    new_text, _, _ = set_ini_key("[Appearance]\nColorScheme=Old\n", "Appearance",
                                 "ColorScheme", value)
    assert parse_ini(new_text)[("Appearance", "ColorScheme")] == value
