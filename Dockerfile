FROM            codecov/baseapi

EXPOSE          8000

COPY            . /app

WORKDIR         /app

RUN             python manage.py collectstatic --no-input
RUN mkdir -p /config
RUN rm /app/utils/config.py
RUN rm /app/codecov/settings_dev.py
RUN rm /app/codecov/settings_prod.py
RUN rm /app/codecov/settings_test.py
RUN rm /app/codecov/settings_staging.py

# Remove unneeded folders
RUN rm -rf /app/.github
RUN rm -rf /app/.circleci
COPY enterprise/config.py /app/utils/config.py