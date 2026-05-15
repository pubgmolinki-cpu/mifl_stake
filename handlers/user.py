from aiogram import Router, F, types
from database import db
from keyboards import main_menu
from datetime import datetime, timedelta

router = Router()

@router.message(F.text == "/start")
async def cmd_start(message: types.Message):
    args = message.text.split()
    referrer_id = int(args[1].replace("ref_", "")) if len(args) > 1 and args[1].startswith("ref_") else None
    
    user = await db.get_user(message.from_user.id)
    if not user:
        await db.register_user(message.from_user.id, message.from_user.username, referrer_id)
        if referrer_id:
            await db.update_balance(referrer_id, 500)
            await db.update_balance(message.from_user.id, 250)
            
    await message.answer("⚽️ Добро пожаловать в FTCL BET BOT!", reply_markup=main_menu())

@router.message(F.text == "👤 Профиль")
async def user_profile(message: types.Message):
    user = await db.get_user(message.from_user.id)
    rank = await db.get_user_rank(message.from_user.id)
    bets = await db.get_user_bets(message.from_user.id)
    
    total_bets = len(bets)
    wins = sum(1 for b in bets if b['status'] == 'won')
    winrate = (wins / total_bets * 100) if total_bets > 0 else 0.0
    
    text = (
        f"👤 **{message.from_user.first_name}**\n\n"
        f"🏆 Место в топе: #{rank}\n"
        f"💰 Баланс: {user['balance']} ⭐️\n\n"
        f"📊 Статистика ставок:\n"
        f"Всего: {total_bets}\n"
        f"✅ Победы: {wins}\n"
        f"🎯 Винрейт: {winrate:.1f}%\n"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🎁 Бонус")
async def daily_bonus(message: types.Message):
    user = await db.get_user(message.from_user.id)
    now = datetime.now()
    
    if user['last_bonus'] and now - user['last_bonus'] < timedelta(days=1):
        remains = timedelta(days=1) - (now - user['last_bonus'])
        hours, remainder = divmod(remains.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        await message.answer(f"❌ Вы уже забрали бонус. Приходите через {hours}ч {minutes}м.")
        return
        
    await db.update_balance(message.from_user.id, 100)
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_bonus = $1 WHERE tg_id = $2", now, message.from_user.id)
        
    await message.answer("🎁 Ежедневный бонус!\n\n💰 Начислено: 100 ⭐️")

@router.message(F.text == "👥 Рефералка")
async def referral_program(message: types.Message):
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    
    async with db.pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1", message.from_user.id)
        
    text = (
        f"👥 **Реферальная программа**\n\n"
        f"🔗 Ваша ссылка:\n`{ref_link}`\n\n"
        f"💰 За каждого друга: 500 ⭐️\n"
        f"🎁 Бонус другу: 250 ⭐️\n\n"
        f"👤 Всего рефералов: {count}"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "🏆 Топ-10")
async def leaderboard(message: types.Message):
    top_users = await db.get_top_users()
    text = "🏆 **Топ-10 Игроков:**\n\n"
    for i, user in enumerate(top_users, 1):
        username = f"@{user['username']}" if user['username'] else "Игрок"
        text += f"{i}. {username} — {user['balance']} ⭐️\n"
    await message.answer(text, parse_mode="Markdown")
