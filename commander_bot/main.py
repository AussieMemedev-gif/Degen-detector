import argparse
from .agents import ChartTraderAgent, OnChainScoutAgent, RiskSecurityAgent, SocialAlphaAgent
from .commander import ChiefCommander
from .config import Settings
from .models import TokenSnapshot
from .notifications import format_alert, send_telegram
from .storage import Ledger


def demo_candidate() -> TokenSnapshot:
    return TokenSnapshot(
        mint="DEMO_MINT_NOT_FOR_TRADING", symbol="DEMO", price_usd=0.00042,
        liquidity_usd=61_000, volume_5m_usd=29_000, volume_change_pct=120,
        unique_buyers_5m=58, buy_sell_ratio=1.9, top10_holder_pct=24,
        mint_authority_active=False, freeze_authority_active=False, sellable=True,
        estimated_slippage_pct=1.2, social_mentions_15m=310, social_velocity_pct=145,
        trusted_kol_mentions=2, price_change_5m_pct=7.5, price_change_1h_pct=21,
        pool_age_minutes=95,
    )


def run_once(settings: Settings) -> str:
    agents = [SocialAlphaAgent(), OnChainScoutAgent(), ChartTraderAgent(), RiskSecurityAgent(settings)]
    decision = ChiefCommander(agents, settings).decide(demo_candidate())
    Ledger(settings.database_path).record(demo_candidate(), decision)
    message = format_alert(decision, settings.bot_display_name)
    send_telegram(settings.telegram_token, settings.telegram_chat_id, message)
    return message


def main() -> None:
    parser = argparse.ArgumentParser(description="Degen Detector paper-trading MVP")
    parser.add_argument("--once", action="store_true", help="Run one demo analysis")
    parser.add_argument("--controls", action="store_true", help="Run Telegram control menu")
    args = parser.parse_args()
    settings = Settings()
    if args.controls:
        from .control import run_control_bot
        run_control_bot(settings)
    else:
        print(run_once(settings))


if __name__ == "__main__":
    main()
