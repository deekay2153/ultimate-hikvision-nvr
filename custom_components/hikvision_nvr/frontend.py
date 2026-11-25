"""Serve the card and register it as a dashboard resource.

The card is shipped inside the integration and added to the dashboard
resources on start, so it works the moment the integration is installed -- no
copying into ``www/`` and no manual resource entry. There is no sidebar panel:
the card does that job on any dashboard.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_BASE = f"/{DOMAIN}_frontend"
# Set once the frontend is registered; also carries the card and panel URLs,
# so its presence is the "already done" flag.
DATA_URLS = f"{DOMAIN}_frontend_urls"


async def _async_asset_urls(hass: HomeAssistant) -> tuple[str, str]:
    """Card and panel URLs, cache-busted by the integration's own version.

    Derived from the manifest rather than kept as its own constant, which drifts:
    a browser caches a failed module fetch hard, so if an upgrade is briefly
    broken and the URL never changes, the failure outlives the fix. Every
    release being a new URL makes that impossible, and leaves nothing to forget
    to bump.
    """
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version or "dev")
    return (
        f"{URL_BASE}/hikvision-nvr-card.js?v={version}",
        f"{URL_BASE}/hikvision-nvr-panel.js?v={version}",
    )


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register the static files and the card resource. Idempotent."""
    if DATA_URLS in hass.data:
        return
    card_url, panel_url = await _async_asset_urls(hass)
    hass.data[DATA_URLS] = (card_url, panel_url)

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                URL_BASE, str(Path(__file__).parent / "frontend"), cache_headers=False
            )
        ]
    )

    # The card is added as a dashboard resource, not injected into every page
    # (add_extra_js_url): injected early it ran before Firefox's custom element
    # support was ready and the card never registered, and the companion app
    # caches the page that carries injected scripts hard. Lovelace may not be
    # set up yet -- we run during async_setup -- so wait for start.
    async_at_started(hass, _async_register_lovelace_resource)

    _LOGGER.debug("Hikvision NVR frontend registered at %s", card_url)


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register the card as a Lovelace resource (or bring its version up to date).

    Resources are delivered over the websocket, so they also reach a companion
    app running a stale cached page.
    """
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        return  # Lovelace not set up (or YAML mode with none defined)
    if not hasattr(resources, "async_create_item"):
        _LOGGER.debug("Lovelace is in YAML mode; add the card resource yourself")
        return

    card_url = hass.data.get(DATA_URLS, (None, None))[0]
    if not card_url:
        return

    try:
        if not getattr(resources, "loaded", True):
            await resources.async_load()
            resources.loaded = True

        stem = card_url.split("?")[0]
        for item in resources.async_items():
            if item.get("url", "").split("?")[0] != stem:
                continue
            if item["url"] == card_url:
                return  # already current
            # Same card, older version: point it at the new one.
            await resources.async_update_item(item["id"], {"url": card_url})
            return
        await resources.async_create_item({"res_type": "module", "url": card_url})
        _LOGGER.debug("Registered %s as a Lovelace resource", card_url)
    except Exception as err:  # noqa: BLE001 - never block setup over a resource
        _LOGGER.debug("Could not register the Lovelace resource: %s", err)
