"""Template Engine for RTL code generation."""

from pathlib import Path
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, BaseLoader


class TemplateEngine:
    """Jinja2-based template engine for code generation."""

    def __init__(self, template_dir: Optional[Path] = None):
        if template_dir and template_dir.exists():
            self.env = Environment(loader=FileSystemLoader(template_dir))
        else:
            self.env = Environment(loader=BaseLoader())

        # Register custom filters
        self._register_filters()

    def _register_filters(self):
        """Register custom Jinja2 filters."""
        self.env.filters['hex'] = lambda x, w=1: f"{w}'h{x:X}"
        self.env.filters['bin'] = lambda x, w=1: f"{w}'b{x:b}"
        self.env.filters['dec'] = lambda x, w=1: f"{w}'d{x}"
        self.env.filters['repeat'] = lambda s, n: s * n
        self.env.filters['indent_lines'] = lambda s, n=4: '\n'.join(' ' * n + line for line in s.split('\n'))

    def load_template(self, template_name: str) -> Any:
        """Load a template from file."""
        return self.env.get_template(template_name)

    def load_template_string(self, template_string: str) -> Any:
        """Load a template from string."""
        return self.env.from_string(template_string)

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render a template with context."""
        template = self.load_template(template_name)
        return template.render(**context)

    def render_string(self, template_string: str, context: Dict[str, Any]) -> str:
        """Render a template string with context."""
        template = self.load_template_string(template_string)
        return template.render(**context)
