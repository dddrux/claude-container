# BUG-007 — janela maximizada ainda mostrava a moldura laranja de 4px
- main.py: o estado maximizado restaurado em __init__ (restoreGeometry) ocorria antes de self.frame existir, então changeEvent ignorava e a moldura ficava. Novo MainWindow._sync_frame() (chamado em changeEvent, resizeEvent e show_window, + retry em 150/200ms); Framed.set_maximized idempotente.
Build: nenhuma dependência nova.
