FROM python:3.13-slim
WORKDIR /bot
ENV PYTHONDONTWRITEBYTECODE=1
COPY bot.py lasercover.py dodge.py cover.py cover.i16 targeting.py loot.py objectives.py first_run.py navigation.py ground.grid grid.json heights.i16 example_bot.py mechfight.py ./
USER 65534:65534
ENTRYPOINT ["python3","-u","/bot/bot.py"]
