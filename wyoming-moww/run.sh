#!/usr/bin/with-contenv bashio

flags=()
if bashio::config.true 'debug'; then
    flags+=('--debug')
fi
if ! bashio::config.true 'verifier'; then
    flags+=('--no-verifier')
fi

exec /usr/src/.venv/bin/python -m moww_wyoming \
    --uri 'tcp://0.0.0.0:10400' \
    --models-dir "$(bashio::config 'models_dir')" \
    --stage1-cutoff "$(bashio::config 'stage1_cutoff')" \
    --verifier-cutoff "$(bashio::config 'verifier_cutoff')" \
    "${flags[@]}"
