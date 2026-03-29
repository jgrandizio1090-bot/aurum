from aurum_voice.web import create_app

# Vercel Python runtime looks for a module-level WSGI application object.
app = create_app(start_background_intelligence=False)
