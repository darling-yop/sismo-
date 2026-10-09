# Casos mínimos de la sección 16: esperado vs obtenido

Generado con `python -m scripts.run_cases`. Reloj de simulación 2026-09-07T12:00:00Z; W=48 h, R=40 km, L=3, T=72 h; estaciones EST-A/B/C; zonas: Valle Central [200.0,200.0]-[500.0,500.0] poblada; Costa [500.0,0.0]-[1000.0,400.0] no poblada; Altiplano [0.0,600.0]-[400.0,1000.0] poblada. Cada caso parte de un escenario vacío salvo que se indique lo contrario.

| Caso | Verificación | Esperado | Obtenido | Resultado |
|---|---|---|---|---|
| 1 Límites y empates | M=4,5, H=30,0 km, zona poblada | prioridad 3 | prioridad 3 | OK |
| 1 Límites y empates | M=4,5, H=30,1 km (supera el límite) | prioridad 2 | prioridad 2 | OK |
| 1 Límites y empates | M=4,5, H=10, epicentro fuera de zona poblada | prioridad 2 | prioridad 2 | OK |
| 1 Límites y empates | M=4,4 (bajo el umbral) | prioridad 1 | prioridad 1 | OK |
| 1 Límites y empates | M=6,0 exacto, profundo y sin población | prioridad 3 | prioridad 3 | OK |
| 1 Límites y empates | M=5,9 profundo y sin población | prioridad 2 | prioridad 2 | OK |
| 1 Límites y empates | epicentro (500,300) sobre el borde Valle(poblada)/Costa | prioridad 3 | prioridad 3 | OK |
| 1 Límites y empates | epicentro (500,450) sobre el borde de Valle | prioridad 3 | prioridad 3 | OK |
| 1 Límites y empates | igual P y M: el desempate es por identificador (inorden) | [21, 22, 23] | [21, 22, 23] | OK |
| 2 Corrección y reporte antiguo | estado inicial M=4,8 H=70,0 | prioridad 2 | prioridad 2 | OK |
| 2 Corrección y reporte antiguo | tras corregir a M=6,2 H=15,0 | prioridad 3, clave (3, 6.2, 20), revisión 2 | prioridad 3, clave (3, 6.2, 20), revisión 2 | OK |
| 2 Corrección y reporte antiguo | reporte con revisión menor (1 < 2) | decisión antiguo | decisión antiguo | OK |
| 2 Corrección y reporte antiguo | no se crea otro nodo ni se revierte | 1 nodo, clave (3, 6.2, 20) | 1 nodo, clave (3, 6.2, 20) | OK |
| 2 Corrección y reporte antiguo | contador de descartados | 1 | 1 | OK |
| 3 Reporte tardío | antes del tardío: referencia de #2 (M4,2) | #1 (M5,6) | #1 (M5,6) | OK |
| 3 Reporte tardío | candidatos de #2 tras el evento M6,1 de las 09:55 | [3, 1] | [3, 1] | OK |
| 3 Reporte tardío | referencia de #2 (mayor magnitud, regla del equipo) | 3 | 3 | OK |
| 3 Reporte tardío | referencia de #1 pasa a #3 (6,1 > 5,6 y ocurrió antes) | 3 | 3 | OK |
| 3 Reporte tardío | el tardío no tiene referencia | None | None | OK |
| 4 Rotaciones y recuperación | caso LL con magnitudes (3.0, 2.0, 1.0) | {'caso': 1, 'giros': 1, 'raíz': 2, 'balanceado': True} | {'caso': 1, 'giros': 1, 'raíz': 2, 'balanceado': True} | OK |
| 4 Rotaciones y recuperación | caso RR con magnitudes (1.0, 2.0, 3.0) | {'caso': 1, 'giros': 1, 'raíz': 2, 'balanceado': True} | {'caso': 1, 'giros': 1, 'raíz': 2, 'balanceado': True} | OK |
| 4 Rotaciones y recuperación | caso LR con magnitudes (3.0, 1.0, 2.0) | {'caso': 1, 'giros': 2, 'raíz': 3, 'balanceado': True} | {'caso': 1, 'giros': 2, 'raíz': 3, 'balanceado': True} | OK |
| 4 Rotaciones y recuperación | caso RL con magnitudes (1.0, 3.0, 2.0) | {'caso': 1, 'giros': 2, 'raíz': 3, 'balanceado': True} | {'caso': 1, 'giros': 2, 'raíz': 3, 'balanceado': True} | OK |
| 4 Rotaciones y recuperación | estrés: cadena de 15 nodos (altura 14), desbalance esperado | True | True | OK |
| 4 Rotaciones y recuperación | diferencia de altura máxima antes de reparar (> 2) | True | True | OK |
| 4 Rotaciones y recuperación | tras recuperar: AVL válido, modo normal | (True, False) | (True, False) | OK |
| 4 Rotaciones y recuperación | conserva identidades | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] | OK |
| 4 Rotaciones y recuperación | conserva el orden (inorden idéntico) | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] | [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] | OK |
| 4 Rotaciones y recuperación | conserva las asociaciones | {1: 15, 2: 15, 3: 15, 4: 15, 5: 15, 6: 15, 7: 15, 8: 15, 9: 15, 10: 15, 11: 15, 12: 15, 13: 15, 14: 15, 15: None} | {1: 15, 2: 15, 3: 15, 4: 15, 5: 15, 6: 15, 7: 15, 8: 15, 9: 15, 10: 15, 11: 15, 12: 15, 13: 15, 14: 15, 15: None} | OK |
| 4 Rotaciones y recuperación | la cola queda en pausa | True | True | OK |
| 4 Rotaciones y recuperación | altura final entre 3 y 4 (cota AVL para 15 nodos) | True | True | OK |
| 5 Archivo masivo | rama elegible con varios eventos: raíz #50, ids [20, 50, 60] | (50, [20, 50, 60]) | (50, [20, 50, 60]) | OK |
| 5 Archivo masivo | tras archivar: activos [100], histórico [20, 50, 60] | ([100], [20, 50, 60]) | ([100], [20, 50, 60]) | OK |
| 5 Archivo masivo | deshacer devuelve el estado completo (una sola acción) | ([20, 50, 60, 100], []) | ([20, 50, 60, 100], []) | OK |
| 5 Archivo masivo | empate de tamaño (1 y 1): gana la raíz más profunda (#55, prof. 2 > #10, prof. 1) | 55 | 55 | OK |
| 5 Archivo masivo | empate de tamaño y profundidad: gana el mayor id (#60) | 60 | 60 | OK |
| 5 Archivo masivo | sin ramas elegibles: se informa y el estado se conserva | (None, True, True) | (None, True, True) | OK |
| 5 Archivo masivo | raíz #10 de prioridad baja con descendiente #30 de prioridad media NO es elegible | (False, 5) | (False, 5) | OK |
| 6 Persistencia y consistencia | topología normal: mismo estado, topología y modo | (True, True, 'normal') | (True, True, 'normal') | OK |
| 6 Persistencia y consistencia | topología en estrés: mismo estado, topología y modo | (True, True, 'stress') | (True, True, 'stress') | OK |
| 6 Persistencia y consistencia | archivo inconsistente: rechazado con problemas listados y sin alterar el estado | (True, True) | (True, True) | OK |
| 6 Persistencia y consistencia | versión restaurada tras reiniciar | True | True | OK |
| 6 Persistencia y consistencia | tras corregir y avanzar la cola: cola 1, #3 con M=6,5 | (1, 6.5) | (1, 6.5) | OK |
| 6 Persistencia y consistencia | deshacer paso de cola y corrección: estado idéntico a la versión | True | True | OK |
| 6 Persistencia y consistencia | deshacer la restauración: escenario vacío | 0 | 0 | OK |

**45 de 45 verificaciones correctas.**
