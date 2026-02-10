set ant 999
set ite 0
battery set 100

atget id id
getpos2 lonSen latSen

loop
wait 10

inc ite
print "Sensor" id "iteracion" ite

read mens
rdata mens tipo valor

if ((tipo == "hola") && (ant == 999))
   set ant valor
   data mens tipo id
   send mens * valor
end

if (tipo == "alerta")
   send mens ant
end

if (tipo == "stop")
   print "Sensor" id "recibio STOP"
   stop
end

areadsensor tempSen
rdata tempSen SensTipo idSens temp

print "Sensor" id "temperatura =" temp

if (temp > 30)
   print "Sensor" id "ENVIA ALERTA"
   data mens "alerta" lonSen latSen
   send mens ant
end

battery bat
print "Sensor" id "bateria =" bat

if (bat < 5)
   print "Sensor" id "BATERIA CRITICA"
   data mens "critico" lonSen latSen
   send mens *
   stop
end

if (ite >= 1000)
   print "Sensor" id "LIMITE DE ITERACIONES"
   stop
end
