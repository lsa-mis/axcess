"""Optional local AI setup for the desktop app (the "AI pack").

Picks a model size for the computer, installs a pinned Ollama when none is
running, downloads the chosen models, and tells the rest of Axcess which
Ollama address and models to use. Report data never leaves the computer;
only the Ollama program and the models are downloaded, and only after the
person asks for it.
"""
