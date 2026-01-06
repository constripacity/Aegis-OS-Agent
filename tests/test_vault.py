

from aegis.core.vault import ClipboardVault


def test_vault_store_and_search(app_config) -> None:
    vault = ClipboardVault(app_config)
    vault.store("Invoice for November")
    results = vault.search("Invoice")
    assert any("Invoice" in item for item in results)
    vault.wipe()
    assert vault.search("Invoice") == []
    vault.close()

