# ===== MAIN (SAFE) =====
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN mancante nelle ENV")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("utenti", utenti))
    app.add_handler(CommandHandler("list", list_users))
    app.add_handler(CommandHandler("export", export_csv))
    app.add_handler(CommandHandler("backup_db", backup_db_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("status", status))

    # post_init viene eseguito quando l'event loop è attivo
    async def _post_init(_app):
        # 1) Togli qualsiasi webhook e droppa gli update pendenti
        try:
            await _app.bot.delete_webhook(drop_pending_updates=True)
            logger.info("[GUARD] webhook rimosso e pending updates droppati")
        except Exception as e:
            logger.warning(f"[GUARD] delete_webhook fallito: {e}")

        # 2) Avvia il backup giornaliero come task (ora il loop è running)
        _app.create_task(daily_backup_loop(_app))
        tok = BOT_TOKEN
        masked = f"{tok[:6]}…{tok[-6:]}" if len(tok) > 12 else "n/a"
        logger.info(f"[START] Polling con token={masked}")

    app.post_init = _post_init

    logger.info("Avvio polling SAFE…")
    app.run_polling(
        close_loop=False,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()