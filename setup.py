from setuptools import setup


setup(
    entry_points={
        "console_scripts": [
            "quote-gen=terminal_quote_generator.cli:main",
        ]
    }
)
