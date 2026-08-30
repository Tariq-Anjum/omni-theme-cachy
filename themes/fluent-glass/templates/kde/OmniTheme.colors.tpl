# Omni Theme color scheme for KDE Plasma 6.
#
# THEME-TIER OVERRIDE: this variant maps the authored
# `popups.background` from this theme's surfaces.toml onto Plasma's
# Tooltip/Complementary sets (the built-in template would derive that
# elevation instead). Resolution order prefers this file whenever
# fluent-glass is activated.
#
# The semantic mapping lives in adapters/kde/colors.py (KDE_COLOR_MAP);
# tests lock this file's output to that model. Section/key names follow
# real Plasma 6 schemes (verified against BreezeDark, Plasma 6.7).
# Colors are KConfig triplets; Qt/KConfig accept spaced or compact forms.

[ColorEffects:Disabled]
Color=56,56,56
ColorAmount=0
ColorEffect=0
ContrastAmount=0.65
ContrastEffect=1
IntensityAmount=0.1
IntensityEffect=2

[ColorEffects:Inactive]
ChangeSelectionColor=true
Color=112,111,110
ColorAmount=0.025
ColorEffect=2
ContrastAmount=0.1
ContrastEffect=2
Enable=false
IntensityAmount=0
IntensityEffect=0

[Colors:Window]
BackgroundNormal={{ background_rgb }}
BackgroundAlternate={{ lighter_background_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

[Colors:View]
BackgroundNormal={{ background_rgb }}
BackgroundAlternate={{ lighter_background_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

[Colors:Button]
BackgroundNormal={{ background_rgb }}
BackgroundAlternate={{ lighter_background_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

[Colors:Selection]
BackgroundNormal={{ selection_rgb }}
BackgroundAlternate={{ selection_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ bright_foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

# Popups/tooltips sit on the authored elevated surface.
[Colors:Tooltip]
BackgroundNormal={{ popups.background_rgb }}
BackgroundAlternate={{ popups.background_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

# Complementary is Plasma 6's second color set (used by UI pieces that
# want contrast against the main scheme); it follows the popup surface.
[Colors:Complementary]
BackgroundNormal={{ popups.background_rgb }}
BackgroundAlternate={{ popups.background_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

[Colors:Header]
BackgroundNormal={{ background_rgb }}
BackgroundAlternate={{ lighter_background_rgb }}
DecorationFocus={{ accent_rgb }}
DecorationHover={{ accent_rgb }}
ForegroundActive={{ accent_rgb }}
ForegroundInactive={{ muted_rgb }}
ForegroundLink={{ info_rgb }}
ForegroundNegative={{ error_rgb }}
ForegroundNormal={{ foreground_rgb }}
ForegroundPositive={{ success_rgb }}
ForegroundNeutral={{ warning_rgb }}
ForegroundVisited={{ accent_secondary_rgb }}

[General]
Name=Omni Theme
ColorScheme=OmniTheme

[KDE]
contrast=4

[WM]
activeBackground={{ lighter_background_rgb }}
activeBlend={{ bright_foreground_rgb }}
activeForeground={{ bright_foreground_rgb }}
inactiveBackground={{ dark_background_rgb }}
inactiveBlend={{ dark_foreground_rgb }}
inactiveForeground={{ dark_foreground_rgb }}
