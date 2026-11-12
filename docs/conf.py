"""Sphinx configuration."""

from importlib.metadata import version as _version

project = "metaquest-teleop"
author = "Gregorio Valenti"
release = _version("metaquest-teleop")
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_immaterial",
]

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3

autodoc_typehints = "signature"
autodoc_member_order = "bysource"
napoleon_google_docstring = False
napoleon_numpy_docstring = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
}
intersphinx_timeout = 30  # seconds: a bad network fails the build instead of hanging it

html_theme = "sphinx_immaterial"
html_title = "metaquest-teleop"
html_favicon = "_static/favicon.svg"
# Tooltips of API objects without their synopsis, which the theme joins with an em dash.
# The page outline lists classes, functions and attributes, not their parameters and fields.
object_description_options = [
    ("py:.*", {"generate_synopses": None, "include_fields_in_toc": False}),
    ("py:parameter", {"include_in_toc": False}),
]
exclude_patterns = ["_build"]

# The layout of Material for MkDocs: the sections of the site as tabs under the header, the
# pages of the current section in the left sidebar, the outline of the page on the right.
html_theme_options = {
    "repo_url": "https://github.com/vigno0405/MetaQuestTeleop",
    "repo_name": "MetaQuestTeleop",
    "icon": {"repo": "fontawesome/brands/github", "logo": "material/hand-back-right"},
    "font": {"text": "Inter", "code": "JetBrains Mono"},
    "features": [
        "navigation.tabs",
        "navigation.tabs.sticky",
        "navigation.top",
        "search.highlight",
        "toc.follow",
        "content.code.copy",
    ],
    "palette": [
        {
            "media": "(prefers-color-scheme: light)",
            "scheme": "default",
            "primary": "custom",  # colors in _static/custom.css
            "accent": "custom",
            "toggle": {"icon": "material/weather-night", "name": "Dark mode"},
        },
        {
            "media": "(prefers-color-scheme: dark)",
            "scheme": "slate",
            "primary": "custom",
            "accent": "custom",
            "toggle": {"icon": "material/weather-sunny", "name": "Light mode"},
        },
    ],
    "globaltoc_collapse": True,
    "toc_title_is_page_title": True,
    "social": [
        {
            "icon": "fontawesome/brands/github",
            "link": "https://github.com/vigno0405/MetaQuestTeleop",
        },
        {
            "icon": "fontawesome/brands/python",
            "link": "https://pypi.org/project/metaquest-teleop/",
        },
    ],
}
html_copy_source = False
html_show_sourcelink = False
html_show_copyright = False
html_static_path = ["_static"]
html_css_files = ["custom.css"]
add_module_names = False
