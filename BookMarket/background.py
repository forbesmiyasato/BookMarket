from datetime import date, timedelta
from sqlalchemy import extract
from BookMarket import S3_BUCKET, mail, db, scheduler
from BookMarket.models import Users, Item
from flask_mail import Message
from flask.templating import render_template
from flask.helpers import url_for

@scheduler.interval_schedule(minutes=1)
def query_for_reminder():
    print("Running job...")
    #Set date from initial posting date to send reminder email
    expire_date = date.today() #- timedelta(days=1)
    
    #Query for all item owners whose posts are older than expire_date (force correct datetime conversion)
    expiring_item_ids = db.session.query(Item.id).filter(
        extract('year',Item.date_posted)<=expire_date.year).filter(
            extract('month', Item.date_posted)<=expire_date.month).filter(
                extract('day', Item.date_posted)<=expire_date.day).all()

    #Loop through each user with an expiring post and send an email reminder
    if expiring_item_ids:
        for item_id in expiring_item_ids:
            item = Item.query.get_or_404(item_id)
            msg = Message('Post Will Expire Soon', sender="pacificubooks@gmail.com", recipients=[item.owner.email], body="Your post will expire soon")
            mail.send(msg)