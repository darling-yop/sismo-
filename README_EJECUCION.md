# SismoLab AVL - ejecución (Windows, Python 3.12)

Desde la raíz del repo:

    python main.py                                              # abre la interfaz Tkinter
    python -m unittest discover -s tests -t .                   # 163 pruebas
    python -m scripts.build_data                                # regenera data/*.json (determinista)
    python -m scripts.run_cases                                 # esperado vs obtenido -> docs/casos_seccion16.md

Archivos de prueba (se eligen con el explorador, pestaña "Archivos y versiones"):
- Carga por inserciones: data/carga_inserciones_{aleatoria,ascendente,descendente}.json
- Carga por topología: data/topologia_normal.json, data/topologia_estres.json, data/topologia_inconsistente.json (debe rechazarse)
- Ráfagas: cargue data/estado_inicial_rafaga.json (topología) y luego data/rafaga_mixta.json en la pestaña "Cola"
