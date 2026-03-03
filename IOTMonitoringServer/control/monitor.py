from argparse import ArgumentError
import ssl
from django.db.models import Avg
from datetime import timedelta, datetime
from receiver.models import Data, Measurement
import paho.mqtt.client as mqtt
import schedule
import time
from django.conf import settings

# Umbral de temperatura promedio (°C) para disparar el evento de parpadeo LED
TEMP_EVENT_THRESHOLD = 30.0

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=settings.MQTT_USER_PUB)


def analyze_data():
    # Consulta todos los datos de la última hora, los agrupa por estación y variable
    # Compara el promedio con los valores límite que están en la base de datos para esa variable.
    # Si el promedio se excede de los límites, se envia un mensaje de alerta.

    print("Calculando alertas...")

    data = Data.objects.filter(
        base_time__gte=datetime.now() - timedelta(hours=1))
    aggregation = data.annotate(check_value=Avg('avg_value')) \
        .select_related('station', 'measurement') \
        .select_related('station__user', 'station__location') \
        .select_related('station__location__city', 'station__location__state',
                        'station__location__country') \
        .values('check_value', 'station__user__username',
                'measurement__name',
                'measurement__max_value',
                'measurement__min_value',
                'station__location__city__name',
                'station__location__state__name',
                'station__location__country__name')
    alerts = 0
    for item in aggregation:
        alert = False

        variable = item["measurement__name"]
        max_value = item["measurement__max_value"] or 0
        min_value = item["measurement__min_value"] or 0

        country = item['station__location__country__name']
        state = item['station__location__state__name']
        city = item['station__location__city__name']
        user = item['station__user__username']

        if item["check_value"] > max_value or item["check_value"] < min_value:
            alert = True

        if alert:
            message = "ALERT {} {} {}".format(variable, min_value, max_value)
            topic = '{}/{}/{}/{}/in'.format(country, state, city, user)
            print(datetime.now(), "Sending alert to {} {}".format(topic, variable))
            client.publish(topic, message)
            alerts += 1

    print(len(aggregation), "dispositivos revisados")
    print(alerts, "alertas enviadas")


def check_temperature_event():
    """
    Nuevo procesamiento de evento:
    1. Consulta la base de datos para obtener la temperatura promedio
       de los últimos 10 minutos, agrupada por estación.
    2. Si la temperatura promedio supera TEMP_EVENT_THRESHOLD (30 °C),
       envía un mensaje EVENT al dispositivo para que active el
       parpadeo del LED integrado como actuador de alerta.
    """

    print("Verificando evento de temperatura...")

    # Consulta: promedio de temperatura de los últimos 10 minutos por estación
    ten_minutes_ago = datetime.now() - timedelta(minutes=10)
    data = Data.objects.filter(
        base_time__gte=ten_minutes_ago,
        measurement__name='temperatura'
    )

    aggregation = data.values(
        'station__user__username',
        'station__location__city__name',
        'station__location__state__name',
        'station__location__country__name',
    ).annotate(avg_temp=Avg('avg_value'))

    events = 0
    for item in aggregation:
        avg_temp = item['avg_temp'] or 0

        country = item['station__location__country__name']
        state = item['station__location__state__name']
        city = item['station__location__city__name']
        user = item['station__user__username']

        if avg_temp > TEMP_EVENT_THRESHOLD:
            # Mensaje con formato: EVENT LED_BLINK <promedio> <umbral>
            message = "EVENT LED_BLINK {:.1f} {:.1f}".format(
                avg_temp, TEMP_EVENT_THRESHOLD)
            topic = '{}/{}/{}/{}/in'.format(country, state, city, user)
            print(datetime.now(),
                  "Evento temp alta -> {} | avg={:.1f}°C".format(topic, avg_temp))
            client.publish(topic, message)
            events += 1

    print(len(aggregation), "estaciones evaluadas para evento de temperatura")
    print(events, "eventos de temperatura enviados")


def on_connect(client, userdata, flags, rc):
    '''
    Función que se ejecuta cuando se conecta al bróker.
    '''
    print("Conectando al broker MQTT...", mqtt.connack_string(rc))


def on_disconnect(client: mqtt.Client, userdata, rc):
    '''
    Función que se ejecuta cuando se desconecta del broker.
    Intenta reconectar al bróker.
    '''
    print("Desconectado con mensaje:" + str(mqtt.connack_string(rc)))
    print("Reconectando...")
    client.reconnect()


def setup_mqtt():
    '''
    Configura el cliente MQTT para conectarse al broker.
    '''

    print("Iniciando cliente MQTT...", settings.MQTT_HOST, settings.MQTT_PORT)
    global client
    try:
        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=settings.MQTT_USER_PUB)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect

        if settings.MQTT_USE_TLS:
            client.tls_set(ca_certs=settings.CA_CRT_PATH,
                           tls_version=ssl.PROTOCOL_TLSv1_2, cert_reqs=ssl.CERT_NONE)

        client.username_pw_set(settings.MQTT_USER_PUB,
                               settings.MQTT_PASSWORD_PUB)
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT)

    except Exception as e:
        print('Ocurrió un error al conectar con el bróker MQTT:', e)


def start_cron():
    '''
    Inicia el cron que se encarga de ejecutar la función analyze_data cada 10 segundos.
    '''
    print("Iniciando cron...")
    schedule.every(10).seconds.do(analyze_data)
    schedule.every(10).seconds.do(check_temperature_event)
    print("Servicio de control iniciado")
    while 1:
        schedule.run_pending()
        time.sleep(1)
