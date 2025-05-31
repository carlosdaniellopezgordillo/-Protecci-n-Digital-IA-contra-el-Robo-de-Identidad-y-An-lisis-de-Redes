import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
import warnings
from statsmodels.tools.sm_exceptions import ConvergenceWarning # Importar específicamente

def generate_predictions(historical_series: pd.Series, n_future_steps: int, order=(5,1,0)):
    """
    Genera predicciones futuras usando un modelo ARIMA de statsmodels.
    
    Args:
        historical_series (pd.Series): Serie temporal con DateTimeIndex y los valores a predecir.
                                       Debe estar ordenada por fecha.
        n_future_steps (int): Número de pasos futuros a predecir.
        order (tuple): El orden (p,d,q) del modelo ARIMA. 
                       (p: auto-regresivo, d: diferenciación, q: media móvil)
                       Un valor común para empezar es (5,1,0) o (1,1,1).
        
    Returns:
        pd.Series: Serie con las predicciones futuras (índice de fechas, valores predichos).
                   Retorna una Serie vacía si no se pueden generar predicciones.
    """
    # ARIMA necesita un mínimo de puntos. Esta es una heurística, puede variar.
    # Generalmente, se necesita al menos p + d + q + algunos puntos extra.
    # Para order=(5,1,0), necesitarías al menos 5 (p) + 1 (d) + algunos más.
    # Si len(historical_series) es menor que sum(order) + 2 (aprox), puede fallar.
    # Vamos a poner un umbral un poco más conservador.
    min_obs_needed = sum(order) + 5 
    if historical_series.empty or len(historical_series) < min_obs_needed:
        print(f"Datos históricos insuficientes para ARIMA con orden {order}. "
              f"Se necesitan al menos {min_obs_needed} puntos, se tienen {len(historical_series)}.")
        return pd.Series(dtype='float64')

    # Asegurar que el índice sea monotónico creciente
    if not historical_series.index.is_monotonic_increasing:
        historical_series = historical_series.sort_index()

    # Intentar inferir la frecuencia si no está presente, default a 'D' (diaria)
    freq = historical_series.index.freq
    if freq is None:
        freq = pd.infer_freq(historical_series.index)
        if freq is None:
            # Si no se puede inferir, y los datos son diarios, asumimos 'D'
            # Esto es importante para generar las fechas futuras correctamente.
            # Si tus datos no son diarios, ajusta esto.
            time_diffs = historical_series.index.to_series().diff().median()
            if time_diffs == pd.Timedelta(days=1):
                freq = 'D'
                # Forzar la frecuencia si se infiere como diaria pero no está explícita
                # Esto ayuda a ARIMA a generar correctamente las fechas futuras.
                historical_series = historical_series.asfreq('D', method='pad') 
            else:
                # Si no es diario y no se puede inferir, ARIMA puede tener problemas
                # con la generación de fechas futuras para la predicción.
                print("Advertencia: No se pudo inferir la frecuencia diaria de la serie temporal. "
                      "Las fechas de predicción podrían no ser precisas o el modelo podría fallar.")
                # Opcionalmente, podrías devolver una serie vacía aquí si la frecuencia es crítica.
                # return pd.Series(dtype='float64') 
                # Por ahora, intentaremos continuar sin forzar una frecuencia no diaria.
                # Si esto causa problemas, considera preprocesar los datos para tener una frecuencia regular.
                pass # Continuar sin frecuencia explícita si no es diaria y no se puede inferir

    try:
        # Statsmodels puede generar muchos warnings, especialmente sobre convergencia
        # o si la serie no es perfectamente estacionaria después de la diferenciación.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            warnings.simplefilter("ignore", FutureWarning)
            warnings.simplefilter("ignore", ConvergenceWarning) # Usar la importación específica

            # Asegurarse de que los datos sean float
            data_for_arima = historical_series.astype(float)

            # Si freq sigue siendo None, ARIMA intentará inferirlo, pero puede fallar o ser inexacto.
            # Es mejor si la serie ya tiene una frecuencia establecida.
            model = ARIMA(data_for_arima, order=order, freq=freq, enforce_stationarity=False, enforce_invertibility=False)
            model_fit = model.fit()
            
            # Generar predicciones
            # El índice de las predicciones de model_fit.predict() o forecast()
            # ya debería ser correcto si la frecuencia se manejó bien.
            predictions = model_fit.forecast(steps=n_future_steps)
            
            return predictions.astype(float)
            
    except Exception as e:
        print(f"Error al generar predicciones con Statsmodels ARIMA (orden {order}): {e}")
        # Podrías intentar con un orden más simple como (1,1,0) como fallback aquí si quisieras.
        return pd.Series(dtype='float64')

# Ejemplo de cómo podrías usar pmdarima si decides instalarlo y usarlo:
# (Asegúrate de instalarlo con: pip install pmdarima)
# import pmdarima as pm
# def generate_predictions_auto_arima(historical_series: pd.Series, n_future_steps: int):
#     """
#     Genera predicciones futuras usando auto_arima de pmdarima.
#     """
#     if historical_series.empty or len(historical_series) < 10: # auto_arima generalmente necesita más datos
#         print("Datos históricos insuficientes para auto_arima.")
#         return pd.Series(dtype='float64')
# 
#     if not historical_series.index.is_monotonic_increasing:
#         historical_series = historical_series.sort_index()
# 
#     # Asegurar frecuencia si es posible, especialmente si es diaria
#     freq = historical_series.index.freq
#     if freq is None:
#         inferred_freq = pd.infer_freq(historical_series.index)
#         if inferred_freq == 'D': # Solo si es claramente diario
#              historical_series = historical_series.asfreq('D', method='pad')
#              freq = 'D' # Actualizar freq para usarlo después
# 
#     try:
#         with warnings.catch_warnings():
#             warnings.simplefilter("ignore") # Suprimir todos los warnings de pmdarima
# 
#             model = pm.auto_arima(historical_series.astype(float),
#                                   start_p=1, start_q=1,
#                                   max_p=5, max_q=5, 
#                                   m=1, # m=1 para series no estacionales. Si tienes estacionalidad (ej. semanal m=7), ajusta.
#                                   start_P=0, seasonal=False, # Poner seasonal=True y ajustar m si es necesario
#                                   d=1, # Dejar que auto_arima encuentre 'd' si es None, o fijarlo si se conoce
#                                   D=0, # Para estacionalidad
#                                   trace=False, # Poner True para ver los modelos que prueba
#                                   error_action='ignore',  # No fallar si un modelo no converge
#                                   suppress_warnings=True, # Suprimir warnings de convergencia
#                                   stepwise=True) # Usar el algoritmo stepwise más rápido
#         
#         # Generar fechas futuras para el índice de la predicción
#         last_date = historical_series.index[-1]
#         
#         # pmdarima.predict devuelve un array numpy. Necesitamos crear el índice de fechas.
#         if freq: # Si tenemos frecuencia, podemos generar un rango de fechas
#             future_dates = pd.date_range(start=last_date, periods=n_future_steps + 1, freq=freq)[1:]
#         else: 
#             # Si no hay frecuencia, no podemos generar un índice de fechas fácilmente.
#             # Esto es una limitación. Podrías generar un índice numérico o intentar inferir del último paso.
#             # Para este ejemplo, si no hay freq, las predicciones no tendrán un índice de fecha adecuado.
#             # En la práctica, es crucial asegurar que la serie tenga una frecuencia.
#             print("Advertencia: No se pudo generar un índice de fechas preciso para las predicciones con auto_arima sin una frecuencia de serie definida.")
#             # Como fallback, creamos un índice numérico si no hay fechas.
#             # O podrías intentar generar fechas asumiendo una diferencia de 1 día si es lo más común.
#             # Por simplicidad, si no hay freq, las predicciones no tendrán un índice de fecha DateTime.
#             # Esto podría causar problemas más adelante en el dashboard si espera un DateTimeIndex.
#             # Una mejor aproximación sería intentar forzar la frecuencia antes de llamar a auto_arima.
#             predicted_values_array = model.predict(n_periods=n_future_steps)
#             return pd.Series(predicted_values_array, name=f"{historical_series.name}_prediccion_auto")
# 
#         predicted_values_array = model.predict(n_periods=n_future_steps)
#         predictions = pd.Series(predicted_values_array, index=future_dates, name=f"{historical_series.name}_prediccion_auto")
#         
#         return predictions.astype(float)
# 
#     except Exception as e:
#         print(f"Error al generar predicciones con auto_arima: {e}")
#         return pd.Series(dtype='float64')

