import os
import secrets
import boto3
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort, jsonify
from BookMarket.models import User, Item, ItemClass, ItemDepartment, ItemImage, SaveForLater
from BookMarket.forms import RegistrationForm, LoginForm, UpdateAccountForm, PostForm, EditForm
from BookMarket import app, db, bcrypt, S3_BUCKET
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.utils import secure_filename


@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html', title="about")


@app.route("/register", methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(
            form.password.data).decode('utf-8')
        user = User(username=form.username.data,
                    email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash(
            f'Hi {form.username.data}! Your account has been created, you can now login!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if (user and bcrypt.check_password_hash(user.password, form.password.data)):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash(f'Welcome {user.username}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password',
                  'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for(
        'static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title='Account', image_file=image_file, form=form)


@app.route("/item/new", methods=['GET', 'POST'])
@login_required
def new_item():
    form = PostForm()
    # form.item_class.choices = class_list
    departments = db.session.query(ItemDepartment).all()
    department_list = [(i.id, i.department_name) for i in departments]
    form.item_department.choices = department_list
    if request.method == 'POST':
        images = form.images.data
        post = Item(name=form.name.data, description=form.description.data, user_id=current_user.id,
                    price=form.price.data, class_id=form.item_class.data, department_id=form.item_department.data)
        db.session.add(post)
        db.session.commit()
        db.session.refresh(post)
        newId = post.id
        if images:
            thumbnail = save_picture(images, newId)
        if thumbnail:
            item = Item.query.filter_by(id=newId).first()
            item.thumbnail = thumbnail
            db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('home'))
    return render_template('create_post.html', title='New Item', form=form, legend='New')


@app.route('/class/<department>')
def item_class(department):
    classes = ItemClass.query.filter_by(department_id=department).all()
    classArray = []
    for item_class in classes:
        classObj = {}
        classObj['id'] = item_class.id
        classObj['department_id'] = item_class.department_id
        classObj['class_name'] = item_class.class_name
        classArray.append(classObj)
    return jsonify({'classes': classArray})


@app.route("/shop")
def shop():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 6, type=int)
    order = request.args.get('order', 'desc')
    date_sorted = getattr(Item.date_posted, order)()
    departments = db.session.query(ItemDepartment).all()
    # for department in departments:
    #     # classObj = {}
    #     classes = ItemClass.query.filter_by(department_id=department.id).all()
    #     department['classes'] = classes
    posts = Item.query.order_by(
        date_sorted).paginate(page=page, per_page=per_page)
    return render_template('shop.html', title='Shop', posts=posts, departments=departments)


@app.route("/shop/<int:item_id>", methods=['GET', 'POST'])
def item(item_id):
    item = Item.query.get_or_404(item_id)
    form = EditForm()
    if request.method == 'POST':
        item.name = form.name.data
        item.description = form.description.data
        item.user_id = current_user.id
        item.price = form.price.data
        item.class_id = form.item_class.data
        item.department_id = form.item_department.data
        db.session.commit()
    images = ItemImage.query.filter_by(item_id=item_id).all()
    item_class = ItemClass.query.get(item.class_id)
    department = ItemDepartment.query.get(item.department_id)
    # for updating
    departments = db.session.query(ItemDepartment).all()
    department_list = [(i.id, i.department_name) for i in departments]
    form.item_department.choices = department_list
    form.name.data = item.name
    form.description.data = item.description
    form.price.data = item.price
    return render_template('single_product.html', title=item.name, item=item, images=images,
                           item_class=item_class, department=department, form=form, legend="Edit")


@app.route("/shop/class/<int:class_id>")
def items_for_class(class_id):
    per_page = request.args.get('per_page', 6, type=int)
    page = request.args.get('page', 1, type=int)
    departments = db.session.query(ItemDepartment).all()
    order = request.args.get('order', 'desc')
    date_sorted = getattr(Item.date_posted, order)()
    item_class = ItemClass.query.get_or_404(class_id)
    posts = Item.query.filter_by(class_id=class_id).order_by(
        date_sorted).paginate(page=page, per_page=per_page)
    return render_template('shop_class.html', title='Shop', posts=posts, departments=departments, class1=item_class)


@app.route("/shop/department/<int:department_id>")
def items_for_department(department_id):
    per_page = request.args.get('per_page', 6, type=int)
    page = request.args.get('page', 1, type=int)
    departments = db.session.query(ItemDepartment).all()
    order = request.args.get('order', 'desc')
    date_sorted = getattr(Item.date_posted, order)()
    department = ItemDepartment.query.get_or_404(department_id)
    posts = Item.query.filter_by(department_id=department_id).order_by(
        date_sorted).paginate(page=page, per_page=per_page)
    return render_template('shop_department.html', title='Shop', posts=posts, departments=departments, department=department)


@app.route('/user/<string:username>')
def user_posts(username):
    page = request.args.get('page', 1, type=int)
    user = User.query.filter_by(username=username).first_or_404()
    posts = Item.query.order_by(Item.date_posted.desc()).filter_by(
        author=user).paginate(page=page, per_page=5)
    return render_template('user_posts.html', posts=posts, user=user)


@app.route('/add-to-bag', methods=['POST'])
def add_to_bag():
    user = request.args.get('user')
    item = request.args.get('item')
    exist = SaveForLater.query.filter_by(item_id=item, user_id=user).first()
    if exist is None:
        new = SaveForLater(item_id=item, user_id=user)
        db.session.add(new)
        db.session.commit()
    user_saved_items = SaveForLater.query.filter_by(user_id=user).count()
    return jsonify({'num_saved': user_saved_items})


@app.route('/saved')
@login_required
def saved_for_later():
    items_ids = db.session.query(SaveForLater.item_id).filter_by(
        user_id=current_user.id).order_by(SaveForLater.id.desc()).all()
    items = []
    for id in items_ids:
        item = Item.query.get(id)
        items.append(item)

    print(items)
    return render_template('saved_for_later.html', title='Saved', posts=items)


@app.route('/saved/delete', methods=['POST'])
@login_required
def delete_saved():
    item = request.args.get('item_id')
    print(item)
    user = request.args.get('user_id')
    deleting_item = SaveForLater.query.filter_by(
        item_id=item, user_id=user).first()
    if deleting_item.user_id != current_user.id:
        abort(403)
    db.session.delete(deleting_item)
    db.session.commit()
    # flash('Item has been deleted', 'success')
    return redirect(url_for('saved_for_later'))


@app.route('/post/delete', methods=['POST'])
@login_required
def delete_item():
    item = request.args.get('item_id')
    deleting_item = Item.query.get_or_404(item)
    item_name = deleting_item.name
    db.session.delete(deleting_item)
    db.session.commit()
    flash(f'Post "{item_name}" has been deleted', 'success')
    return redirect(url_for('shop'))


@app.route('/post/update', methods=['POST'])
@login_required
def edit_item():
    item = request.args.get('item_id')
    post = Item.query.get_or_404(item)
    if post.owner != current_user:
        abort(403)
    # form = PostForm()
    # if form.validate_on_submit():
    #     post.title = form.title.data
    #     post.content = form.content.data
    #     db.session.commit()
    #     flash('Your post has been updated!', 'success')
    #     return redirect(url_for('post', post_id=post.id))
    # elif request.method == 'GET':
    #     form.title.data = post.title
    #     form.content.data = post.content
    return redirect(url_for('shop'), item_id=item)
# Utility functions


def save_picture(form_images, item_id):
    thumbnail = None
    for index, images in enumerate(form_images):
        if images:
            random_hex = secrets.token_hex(8)
            _, f_ext = os.path.splitext(images.filename)
            picture_fn = random_hex + f_ext
            if (index == 0):
                thumbnail = picture_fn
            # picture_path = os.path.join(
            #     app.root_path, 'static/item_pics', picture_fn)
            # output_size = (183, 195)
            # # output_resolution = (1000, 1000)
            # resizedImage = Image.open(images)
            # # resizedImage.thumbnail(output_resolution)
            # resizedImage = resizedImage.resize(output_size, Image.ANTIALIAS)
            # resizedImage.save(picture_path)
            s3_resource = boto3.resource('s3')
            my_bucket = s3_resource.Bucket(S3_BUCKET)
            my_bucket.Object(picture_fn).put(Body=images)
            newImage = ItemImage(item_id=item_id, image_file=picture_fn)
            db.session.add(newImage)
            db.session.commit()
    return thumbnail
    # #remove use previous profile pic in file system so it doesn't get overloaded
    # if (current_user.image_file != 'default.jpg'):
    #     current_picture_path = os.path.join(app.root_path, 'static/profile_pics', current_user.image_file)
    #     if os.path.exists(current_picture_path):
    #         os.remove(current_picture_path)


# def download_file(file_name):
#     """
#     Function to download a given file from an S3 bucket
#     """
#     s3 = boto3.resource('s3')
#     output = f"downloads/{file_name}"
#     s3.Bucket(S3_BUCKET).download_file(file_name, output)

#     return output
