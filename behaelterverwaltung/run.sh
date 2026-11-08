#!/command/with-contenv bashio

bashio::log.info "Starte Behälterverwaltung ..."
cd /opt/behaelterverwaltung
exec python3 -m app
