#!/bin/bash
cd /var/app/staging/tabbycat
# pipenv shell
# export PYTHONPATH=/var/app/venv/staging-LQM1lest/bin:/var/app/staging/tabbycat
export DJANGO_SETTINGS_MODULE=settings

echo $PYTHONPATH

echo "-----> Running database migration - Skipped"
#python manage.py migrate_schemas --noinput

echo "-----> Running dynamic preferences checks"
python manage.py checkpreferences_schemas --tenant

echo "-----> Running static files compilation - Skipped"
#npm run build
#python manage.py collectstatic --noinput
