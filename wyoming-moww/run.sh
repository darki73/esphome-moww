#!/usr/bin/with-contenv bashio

cd /usr/src || bashio::exit.nok "missing /usr/src"

flags=()
if bashio::config.true 'debug'; then
    flags+=('--debug')
fi
if ! bashio::config.true 'verifier'; then
    flags+=('--no-verifier')
fi
if bashio::config.true 'save_audio'; then
    flags+=('--save-audio')
fi

# Announce the service so the Wyoming integration auto-discovers it
bashio::discovery "wyoming" "$(bashio::var.json uri "tcp://${HOSTNAME}:10400")" > /dev/null || \
    bashio::log.warning "Wyoming discovery announcement failed (add manually: localhost:10400)"

exec /usr/src/.venv/bin/python -m moww_wyoming \
    --uri 'tcp://0.0.0.0:10400' \
    --models-dir "$(bashio::config 'models_dir')" \
    --stage1-cutoff "$(bashio::config 'stage1_cutoff')" \
    --verifier-cutoff "$(bashio::config 'verifier_cutoff')" \
    "${flags[@]}"
