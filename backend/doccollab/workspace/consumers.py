import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError
from .models import File, FileContent
from users.models import TeamMember

logger = logging.getLogger(__name__)
User = get_user_model()

class DocumentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("WebSocket connection attempt")
        await self.accept()
        self.rooms = set()
        self.user = None
        logger.info("WebSocket connection accepted")

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected with code: {close_code}")
        # Leave all rooms
        for room_id in list(self.rooms):
            await self.leave_room(room_id)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            logger.info(f"WebSocket received: {data.get('type')}")
            
            if data.get('type') == 'auth':
                # Authenticate user
                token = data.get('token')
                if not token:
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'Authentication required'
                    }))
                    await self.close(code=4001)
                    return
                
                try:
                    # Verify token
                    token_obj = AccessToken(token)
                    user_id = token_obj['user_id']
                    self.user = await self.get_user(user_id)
                    
                    if not self.user:
                        await self.send(json.dumps({
                            'type': 'error',
                            'message': 'Invalid token'
                        }))
                        await self.close(code=4001)
                        return
                    
                    await self.send(json.dumps({
                        'type': 'auth_success',
                        'message': 'Authentication successful'
                    }))
                    logger.info(f"WebSocket authenticated for user: {self.user.email}")
                    
                except TokenError as e:
                    logger.error(f"Token error: {str(e)}")
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'Invalid token'
                    }))
                    await self.close(code=4001)
                    return
            
            elif data.get('type') == 'join':
                # Join room
                file_id = data.get('fileId')
                if not file_id:
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'File ID required'
                    }))
                    return
                
                # Check if user has access to this file
                has_access = await self.check_file_access(file_id)
                if not has_access:
                    await self.send(json.dumps({
                        'type': 'error',
                        'message': 'You do not have permission to access this file'
                    }))
                    return
                
                await self.join_room(file_id)
                
                await self.send(json.dumps({
                    'type': 'join_success',
                    'fileId': file_id
                }))
                logger.info(f"User {self.user.email} joined room for file: {file_id}")
            
            elif data.get('type') == 'leave':
                # Leave room
                file_id = data.get('fileId')
                if file_id:
                    await self.leave_room(file_id)
                    logger.info(f"User {self.user.email} left room for file: {file_id}")
            
            elif data.get('type') == 'content-change':
                # Broadcast content change
                file_id = data.get('fileId')
                content = data.get('content')
                
                if file_id and content and file_id in self.rooms:
                    # Save content to database
                    await self.save_content(file_id, content)
                    
                    # Broadcast to other clients
                    await self.channel_layer.group_send(
                        f'file_{file_id}',
                        {
                            'type': 'content_update',
                            'fileId': file_id,
                            'content': content,
                            'sender_channel_name': self.channel_name
                        }
                    )
                    logger.info(f"Content change broadcast for file: {file_id}")
        except Exception as e:
            logger.error(f"Error in WebSocket receive: {str(e)}")
            await self.send(json.dumps({
                'type': 'error',
                'message': f'Error processing message: {str(e)}'
            }))

    async def content_update(self, event):
        # Send content update to WebSocket
        if self.channel_name != event['sender_channel_name']:
            await self.send(json.dumps({
                'type': 'content-updated',
                'fileId': event['fileId'],
                'content': event['content']
            }))

    async def join_room(self, file_id):
        # Join room group
        await self.channel_layer.group_add(
            f'file_{file_id}',
            self.channel_name
        )
        self.rooms.add(file_id)

    async def leave_room(self, file_id):
        # Leave room group
        await self.channel_layer.group_discard(
            f'file_{file_id}',
            self.channel_name
        )
        self.rooms.discard(file_id)

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def check_file_access(self, file_id):
        try:
            file = File.objects.select_related('workspace').get(id=file_id)
            
            # Check if user is the owner
            if file.workspace.user == self.user:
                return True
                
            # Check if user is a team member
            team_member = TeamMember.objects.filter(
                user=self.user,
                invited_by=file.workspace.user
            ).exists()
            
            return team_member
        except File.DoesNotExist:
            return False
            
    @database_sync_to_async
    def save_content(self, file_id, content):
        try:
            file = File.objects.get(id=file_id)
            FileContent.objects.update_or_create(
                file=file,
                defaults={'content': content}
            )
            return True
        except Exception as e:
            logger.error(f"Error saving content: {str(e)}")
            return False
