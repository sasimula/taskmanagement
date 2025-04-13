from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import google.oauth2.id_token
from google.auth.transport import requests
from google.cloud import firestore
from starlette.status import HTTP_302_FOUND
from typing import Optional, List
import datetime
import os
from google.oauth2 import service_account

# Set up credentials for local development
# This approach uses approved libraries, not firebase-admin
try:
    if os.path.exists("service-account-key.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account-key.json"
        print("Using local service account credentials")
except Exception as e:
    print(f"Error setting credentials: {e}")

# define the app that will contain all of our routing for Fast API
app = FastAPI()

# define a firestore client so we can interact with our database
firestore_db = firestore.Client()

# we need a request object to be able to talk to firebase for verifying user logins
firebase_request_adapter = requests.Request()

# define the static and templates directories
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Function that we will use to validate an id_token. Will return the user_token if valid, None if not
def validate_firebase_token(id_token):
    # If we don't have a token then return None
    if not id_token:
        print("No ID token found in cookie")
        return None
    
    # try to validate the token. If this fails with an exception then this will remain as None so just return at the end
    # if we got an exception then log the exception before returning
    user_token = None
    try:
        user_token = google.oauth2.id_token.verify_firebase_token(id_token, firebase_request_adapter)
        print(f"Successfully validated token for user: {user_token.get('email') if user_token else 'None'}")
    except ValueError as err:
        # Dump this message to console as it will not be displayed on the template. Use for debugging but if you are building for
        # production you should handle this much more gracefully.
        print(f"Token validation error: {str(err)}")
    
    # return the token to the caller
    return user_token

# Function that we will use to retrieve and return the document that represents this user
# by using the ID of the firebase credentials. This function assumes that the credentials have
# been checked first
def get_user(user_token):
    # now that we have a user token we are going to try and retrieve a user object for this user from firestore if there
    # is not a user object for this user we will create one
    user = firestore_db.collection('users').document(user_token['user_id'])
    if not user.get().exists:
        user_data = {
            'name': user_token['email'],  # Use email as the default name
            'email': user_token['email'],
            'created_boards': [],
            'member_boards': []
        }
        firestore_db.collection('users').document(user_token['user_id']).set(user_data)
    
    # return the user document
    return user

# Route for the main page
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Query firebase for the request token. We also declare a bunch of other variables here as we will need them
    # for rendering the template at the end. We have an error_message there in case you want to output an error to
    # the user in the template.
    id_token = request.cookies.get("token")
    error_message = "-"
    user_token = None
    user = None
    
    # Check if we have a valid firebase login if not return the template with empty data as we will show the login box
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return templates.TemplateResponse("main.html", {"request": request, "user_token": None, "error_message": None, "user_info": None})
    
    # Get the user document and boards
    user = get_user(user_token)
    user_data = user.get().to_dict()
    
    # Get all boards the user has created or is a member of
    created_boards = []
    for board_id in user_data.get('created_boards', []):
        board = firestore_db.collection('boards').document(board_id).get()
        if board.exists:
            board_data = board.to_dict()
            board_data['id'] = board_id
            board_data['is_creator'] = True
            created_boards.append(board_data)
    
    member_boards = []
    for board_id in user_data.get('member_boards', []):
        board = firestore_db.collection('boards').document(board_id).get()
        if board.exists:
            board_data = board.to_dict()
            board_data['id'] = board_id
            board_data['is_creator'] = False
            member_boards.append(board_data)
    
    # Combine all boards
    all_boards = created_boards + member_boards
    
    return templates.TemplateResponse("main.html", {
        "request": request, 
        "user_token": user_token, 
        "error_message": error_message, 
        "user_info": user_data,
        "boards": all_boards
    })

# Login route
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Check if user is already logged in
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    
    # If already logged in, redirect to home
    if user_token:
        return RedirectResponse("/")
    
    return templates.TemplateResponse("login.html", {
        "request": request
    })

# Register route
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    # Check if user is already logged in
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    
    # If already logged in, redirect to home
    if user_token:
        return RedirectResponse("/")
    
    return templates.TemplateResponse("register.html", {
        "request": request
    })

# Route to create a new board
@app.post("/create-board", response_class=RedirectResponse)
async def create_board(request: Request, board_name: str = Form(...)):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the user
    user = get_user(user_token)
    user_data = user.get().to_dict()
    
    # Create a new board
    new_board = {
        'name': board_name,
        'creator_id': user_token['user_id'],
        'creator_email': user_token['email'],
        'created_at': datetime.datetime.now(),
        'members': [user_token['user_id']]  # Creator is automatically a member
    }
    
    # Add the board to Firestore
    board_ref = firestore_db.collection('boards').document()
    board_ref.set(new_board)
    
    # Update the user's created_boards list
    created_boards = user_data.get('created_boards', [])
    created_boards.append(board_ref.id)
    
    user.update({
        'created_boards': created_boards
    })
    
    return RedirectResponse("/", status_code=HTTP_302_FOUND)

# Route to create new board page
@app.get("/new-board", response_class=HTMLResponse)
async def new_board_page(request: Request):
    # Validate user is logged in
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    return templates.TemplateResponse("create_board.html", {
        "request": request,
        "user_token": user_token
    })

# Route to user profile page
@app.get("/profile", response_class=HTMLResponse)
async def user_profile(request: Request):
    # Validate user is logged in
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get user data
    user = get_user(user_token)
    user_data = user.get().to_dict()
    
    return templates.TemplateResponse("user_profile.html", {
        "request": request,
        "user_token": user_token,
        "user_info": user_data
    })

# Route to view a board
@app.get("/board/{board_id}", response_class=HTMLResponse)
async def view_board(request: Request, board_id: str):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if user is authorized to view this board
    if user_token['user_id'] not in board_data['members']:
        return RedirectResponse("/")
    
    # Get all tasks for this board
    tasks_ref = firestore_db.collection('tasks').where('board_id', '==', board_id).stream()
    tasks = []
    
    active_tasks = 0
    completed_tasks = 0
    
    for task in tasks_ref:
        task_data = task.to_dict()
        task_data['id'] = task.id
        
        # If task is completed, add the completion status
        if task_data.get('completed', False):
            completed_tasks += 1
        else:
            active_tasks += 1
            
        # Check if task is unassigned (was assigned to someone who was removed)
        if task_data.get('assigned_to') is None or (
            task_data.get('assigned_to') and 
            task_data['assigned_to'] not in board_data['members']
        ):
            task_data['unassigned'] = True
        else:
            task_data['unassigned'] = False
            
        tasks.append(task_data)
    
    # Get all users for the board
    board_members = []
    for user_id in board_data['members']:
        user_ref = firestore_db.collection('users').document(user_id).get()
        if user_ref.exists:
            member_data = user_ref.to_dict()
            member_data['id'] = user_id
            member_data['is_creator'] = (user_id == board_data['creator_id'])
            board_members.append(member_data)
    
    # Determine if current user is the creator
    is_creator = (user_token['user_id'] == board_data['creator_id'])
    
    return templates.TemplateResponse("board.html", {
        "request": request,
        "user_token": user_token,
        "board": board_data,
        "board_id": board_id,
        "tasks": tasks,
        "members": board_members,
        "is_creator": is_creator,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "total_tasks": active_tasks + completed_tasks
    })

@app.post("/add-task", response_class=RedirectResponse)
async def add_task(
    request: Request, 
    board_id: str = Form(...),
    title: str = Form(...),
    due_date: str = Form(...),
    assigned_to: Optional[str] = Form(None)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board to verify membership
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if user is authorized to add a task to this board
    if user_token['user_id'] not in board_data['members']:
        return RedirectResponse("/")
    
    # Check if a task with the same name already exists on this board
    duplicate_tasks = list(firestore_db.collection('tasks')
                         .where('board_id', '==', board_id)
                         .where('title', '==', title)
                         .limit(1)
                         .stream())
    
    if duplicate_tasks:
        # Redirect back to board with error message
        return RedirectResponse(f"/board/{board_id}?error=duplicate_task", status_code=HTTP_302_FOUND)
    
    # Create a new task
    new_task = {
        'title': title,
        'due_date': due_date,
        'created_by': user_token['user_id'],
        'created_at': datetime.datetime.now(),
        'board_id': board_id,
        'completed': False,
        'completion_date': None,
        'assigned_to': assigned_to if assigned_to else None,
        'unassigned': False if assigned_to else True  # Mark as unassigned if no user assigned
    }
    
    # Add the task to Firestore
    task_ref = firestore_db.collection('tasks').document()
    task_ref.set(new_task)
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# # Route to add a task
# @app.post("/add-task", response_class=RedirectResponse)
# async def add_task(
#     request: Request, 
#     board_id: str = Form(...),
#     title: str = Form(...),
#     due_date: str = Form(...),
#     assigned_to: Optional[str] = Form(None)
# ):
#     # Check for token and validate
#     id_token = request.cookies.get("token")
#     user_token = validate_firebase_token(id_token)
#     if not user_token:
#         return RedirectResponse("/")
    
#     # Get the board to verify membership
#     board_ref = firestore_db.collection('boards').document(board_id)
#     board = board_ref.get()
    
#     if not board.exists:
#         return RedirectResponse("/")
    
#     board_data = board.to_dict()
    
#     # Check if user is authorized to add a task to this board
#     if user_token['user_id'] not in board_data['members']:
#         return RedirectResponse("/")
    
#     # Create a new task
#     new_task = {
#         'title': title,
#         'due_date': due_date,
#         'created_by': user_token['user_id'],
#         'created_at': datetime.datetime.now(),
#         'board_id': board_id,
#         'completed': False,
#         'completion_date': None,
#         'assigned_to': assigned_to if assigned_to else None
#     }
    
#     # Add the task to Firestore
#     task_ref = firestore_db.collection('tasks').document()
#     task_ref.set(new_task)
    
#     return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# Route to mark a task as complete/incomplete
@app.post("/toggle-task", response_class=RedirectResponse)
async def toggle_task(
    request: Request,
    task_id: str = Form(...),
    board_id: str = Form(...)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board to verify membership
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if user is authorized to modify tasks on this board
    if user_token['user_id'] not in board_data['members']:
        return RedirectResponse("/")
    
    # Get the task
    task_ref = firestore_db.collection('tasks').document(task_id)
    task = task_ref.get()
    
    if not task.exists:
        return RedirectResponse(f"/board/{board_id}")
    
    task_data = task.to_dict()
    
    # Toggle the completed status
    new_completed_status = not task_data.get('completed', False)
    
    # Update the task
    update_data = {
        'completed': new_completed_status
    }
    
    # If marking as complete, add the completion date
    if new_completed_status:
        update_data['completion_date'] = datetime.datetime.now()
    else:
        update_data['completion_date'] = None
    
    task_ref.update(update_data)
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# Route to delete a task
@app.post("/delete-task", response_class=RedirectResponse)
async def delete_task(
    request: Request,
    task_id: str = Form(...),
    board_id: str = Form(...)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board to verify membership
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if user is authorized to delete tasks on this board
    if user_token['user_id'] not in board_data['members']:
        return RedirectResponse("/")
    
    # Delete the task
    task_ref = firestore_db.collection('tasks').document(task_id)
    task_ref.delete()
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# Route to edit a task
@app.post("/edit-task", response_class=RedirectResponse)
async def edit_task(
    request: Request,
    task_id: str = Form(...),
    board_id: str = Form(...),
    title: str = Form(...),
    due_date: str = Form(...),
    assigned_to: Optional[str] = Form(None)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board to verify membership
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if user is authorized to edit tasks on this board
    if user_token['user_id'] not in board_data['members']:
        return RedirectResponse("/")
    
    task_ref = firestore_db.collection('tasks').document(task_id)
    
    # Check if the task was previously unassigned and is now assigned
    task = task_ref.get()
    task_data = task.to_dict()
    
    update_data = {
        'title': title,
        'due_date': due_date,
        'assigned_to': assigned_to if assigned_to else None
    }
    
    # Remove unassigned flag if task is now assigned to a user
    if assigned_to and task_data.get('unassigned', False):
        update_data['unassigned'] = False
    
    task_ref.update(update_data)
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# Route to add a user to a board
@app.post("/add-user-to-board", response_class=RedirectResponse)
async def add_user_to_board(
    request: Request,
    board_id: str = Form(...),
    user_email: str = Form(...)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if current user is the creator of the board
    if user_token['user_id'] != board_data['creator_id']:
        return RedirectResponse(f"/board/{board_id}")
    
    # Find user by email
    users_ref = firestore_db.collection('users').where('email', '==', user_email).stream()
    found_user = None
    
    for user in users_ref:
        found_user = user
        break
    
    if not found_user:
        return RedirectResponse(f"/board/{board_id}")
    
    user_id = found_user.id
    user_data = found_user.to_dict()
    
    # Check if user is already a member
    if user_id in board_data['members']:
        return RedirectResponse(f"/board/{board_id}")
    
    # Add user to board members
    board_data['members'].append(user_id)
    board_ref.update({
        'members': board_data['members']
    })
    
    # Add board to user's member_boards
    member_boards = user_data.get('member_boards', [])
    if board_id not in member_boards:
        member_boards.append(board_id)
        
    firestore_db.collection('users').document(user_id).update({
        'member_boards': member_boards
    })
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# Route to remove a user from a board
@app.post("/remove-user-from-board", response_class=RedirectResponse)
async def remove_user_from_board(
    request: Request,
    board_id: str = Form(...),
    user_id: str = Form(...)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if current user is the creator of the board
    if user_token['user_id'] != board_data['creator_id']:
        return RedirectResponse(f"/board/{board_id}")
    
    # Cannot remove yourself (the creator)
    if user_id == board_data['creator_id']:
        return RedirectResponse(f"/board/{board_id}")
    
    # Remove user from board members
    if user_id in board_data['members']:
        board_data['members'].remove(user_id)
        board_ref.update({
            'members': board_data['members']
        })
    
    # Remove board from user's member_boards
    user_ref = firestore_db.collection('users').document(user_id)
    user = user_ref.get()
    
    if user.exists:
        user_data = user.to_dict()
        member_boards = user_data.get('member_boards', [])
        
        if board_id in member_boards:
            member_boards.remove(board_id)
            user_ref.update({
                'member_boards': member_boards
            })
    
    # Mark all tasks assigned to this user as unassigned
    tasks_ref = firestore_db.collection('tasks').where('board_id', '==', board_id).where('assigned_to', '==', user_id).stream()
    
    for task in tasks_ref:
        firestore_db.collection('tasks').document(task.id).update({
            'assigned_to': None,
            'unassigned': True  # Explicitly mark as unassigned
        })
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)
# Route to rename a board
@app.post("/rename-board", response_class=RedirectResponse)
async def rename_board(
    request: Request,
    board_id: str = Form(...),
    new_name: str = Form(...)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if current user is the creator of the board
    if user_token['user_id'] != board_data['creator_id']:
        return RedirectResponse(f"/board/{board_id}")
    
    # Rename the board
    board_ref.update({
        'name': new_name
    })
    
    return RedirectResponse(f"/board/{board_id}", status_code=HTTP_302_FOUND)

# Route to delete a board
@app.post("/delete-board", response_class=RedirectResponse)
async def delete_board(
    request: Request,
    board_id: str = Form(...)
):
    # Check for token and validate
    id_token = request.cookies.get("token")
    user_token = validate_firebase_token(id_token)
    if not user_token:
        return RedirectResponse("/")
    
    # Get the board
    board_ref = firestore_db.collection('boards').document(board_id)
    board = board_ref.get()
    
    if not board.exists:
        return RedirectResponse("/")
    
    board_data = board.to_dict()
    
    # Check if current user is the creator of the board
    if user_token['user_id'] != board_data['creator_id']:
        return RedirectResponse("/")
    
    # Check if there are non-owner users on the board
    if len(board_data['members']) > 1:
        return RedirectResponse(f"/board/{board_id}")
    
    # Check if there are tasks on the board
    tasks_ref = firestore_db.collection('tasks').where('board_id', '==', board_id).limit(1).stream()
    has_tasks = False
    for _ in tasks_ref:
        has_tasks = True
        break
    
    if has_tasks:
        return RedirectResponse(f"/board/{board_id}")
    
    # Remove board from creator's created_boards
    user_ref = firestore_db.collection('users').document(user_token['user_id'])
    user = user_ref.get()
    
    if user.exists:
        user_data = user.to_dict()
        created_boards = user_data.get('created_boards', [])
        
        if board_id in created_boards:
            created_boards.remove(board_id)
            user_ref.update({
                'created_boards': created_boards
            })
    
    # Delete the board
    board_ref.delete()
    
    return RedirectResponse("/", status_code=HTTP_302_FOUND)

# Add an error handler for internal server errors
@app.exception_handler(500)
async def internal_error(request: Request, exc: Exception):
    return templates.TemplateResponse("error.html", {
        "request": request,
        "error_message": str(exc)
    })