import json
import uuid
import requests
from bs4 import BeautifulSoup
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Workspace, File, FileContent
from .serializers import WorkspaceSerializer, FileSerializer, ScrapeWebsiteSerializer, SaveContentSerializer
from users.models import TeamMember, User
import re
import logging

logger = logging.getLogger(__name__)

class WorkspaceListView(generics.ListCreateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Workspace.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_workspace(request):
    # Get user's workspace or create one
    workspace, created = Workspace.objects.get_or_create(
        user=request.user,
        defaults={'name': 'My Workspace'}
    )
    
    # Get root folders
    root_files = File.objects.filter(
        workspace=workspace,
        parent=None
    )
    
    # Build file tree
    file_tree = []
    for file in root_files:
        file_tree.append(build_file_tree(file))
    
    return Response({'fileTree': file_tree})

def build_file_tree(file):
    result = {
        'id': str(file.id),
        'name': file.name,
        'type': file.type
    }
    
    if file.type == 'folder':
        children = File.objects.filter(parent=file)
        result['children'] = [build_file_tree(child) for child in children]
    
    return result

def html_to_tiptap_json(html_content, title=""):
    """Convert HTML content to Tiptap JSON format."""
    try:
        # Create the base document structure
        doc = {
            "type": "doc",
            "content": []
        }
        
        # Add title as h1 if provided
        if title:
            doc["content"].append({
                "type": "heading",
                "attrs": {"level": 1},
                "content": [{"type": "text", "text": title}]
            })
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Process each element
        for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'a', 'img', 'code', 'pre', 'blockquote']):
            if element.name.startswith('h') and len(element.name) == 2:
                # Handle headings
                level = int(element.name[1])
                doc["content"].append({
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": [{"type": "text", "text": element.get_text()}]
                })
            elif element.name == 'p':
                # Handle paragraphs
                paragraph = {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": element.get_text()}]
                }
                doc["content"].append(paragraph)
            elif element.name == 'ul':
                # Handle unordered lists
                list_item = {
                    "type": "bulletList",
                    "content": []
                }
                for li in element.find_all('li', recursive=False):
                    list_item["content"].append({
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": li.get_text()}]
                        }]
                    })
                doc["content"].append(list_item)
            elif element.name == 'ol':
                # Handle ordered lists
                list_item = {
                    "type": "orderedList",
                    "content": []
                }
                for li in element.find_all('li', recursive=False):
                    list_item["content"].append({
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": li.get_text()}]
                        }]
                    })
                doc["content"].append(list_item)
            elif element.name == 'blockquote':
                # Handle blockquotes
                doc["content"].append({
                    "type": "blockquote",
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": element.get_text()}]
                    }]
                })
            elif element.name == 'pre':
                # Handle code blocks
                doc["content"].append({
                    "type": "codeBlock",
                    "content": [{"type": "text", "text": element.get_text()}]
                })
        
        # If no content was added, add an empty paragraph
        if not doc["content"]:
            doc["content"].append({
                "type": "paragraph",
                "content": [{"type": "text", "text": ""}]
            })
        
        return doc
    except Exception as e:
        logger.error(f"Error converting HTML to Tiptap JSON: {str(e)}")
        # Return a simple document with the error
        return {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": f"Error processing content: {str(e)}"}]
                }
            ]
        }

def extract_content_sections(soup, url):
    """Extract content sections from the soup object."""
    # Try to find the main content area
    main_content = None
    
    # Common content selectors
    content_selectors = [
        'main', 'article', '.content', '#content', '.main-content', '#main-content',
        '.post-content', '.entry-content', '.article-content'
    ]
    
    # Try each selector
    for selector in content_selectors:
        content = soup.select_one(selector)
        if content and len(content.get_text(strip=True)) > 100:
            main_content = content
            break
    
    # If no main content found, use the body
    if not main_content:
        main_content = soup.body
    
    # Extract headings to create sections
    headings = main_content.find_all(['h1', 'h2', 'h3', 'h4'], recursive=True)
    
    # If no headings found, return the whole content as one section
    if not headings:
        return [{
            'title': soup.title.string if soup.title else "Untitled Document",
            'content': str(main_content)
        }]
    
    # Create sections based on headings
    sections = []
    for i, heading in enumerate(headings):
        title = heading.get_text(strip=True)
        if not title:
            title = f"Section {i+1}"
        
        # Get content until next heading
        content = ""
        next_node = heading.next_sibling
        
        # Collect all content until the next heading
        while next_node:
            if next_node.name in ['h1', 'h2', 'h3', 'h4'] and next_node in headings:
                break
            if next_node.name:
                content += str(next_node)
            next_node = next_node.next_sibling
        
        # If content is too short, it might be just a heading without content
        if len(content.strip()) < 50:
            # Try to get the parent container
            parent = heading.parent
            if parent and parent.name not in ['body', 'html']:
                content = str(parent)
        
        sections.append({
            'title': title,
            'content': f"<{heading.name}>{title}</{heading.name}>{content}"
        })
    
    return sections

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def scrape_website(request):
    serializer = ScrapeWebsiteSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    url = serializer.validated_data['url']
    
    try:
        # Fetch the website content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title = soup.title.string if soup.title else "Untitled Document"
        
        # Get or create workspace
        workspace, created = Workspace.objects.get_or_create(
            user=request.user,
            defaults={'name': 'My Workspace'}
        )
        
        # Create a root folder for the scraped content
        root_folder = File.objects.create(
            workspace=workspace,
            name=title,
            type='folder',
            parent=None
        )
        
        # Extract content sections
        sections = extract_content_sections(soup, url)
        
        file_tree = []
        
        for section in sections:
            section_title = section['title']
            section_content = section['content']
            
            # Create file in database
            file = File.objects.create(
                workspace=workspace,
                name=section_title,
                type='file',
                parent=root_folder
            )
            
            # Convert HTML to Tiptap JSON
            tiptap_content = html_to_tiptap_json(section_content, section_title)
            
            # Create file content
            file_content = FileContent.objects.create(
                file=file,
                content=tiptap_content
            )
            
            # Add to file tree
            file_tree.append({
                "id": str(file.id),
                "name": section_title,
                "type": "file"
            })
        
        # Build complete file tree
        complete_file_tree = [{
            "id": str(root_folder.id),
            "name": root_folder.name,
            "type": "folder",
            "children": file_tree
        }]
        
        return Response({
            "message": "Website scraped successfully", 
            "fileTree": complete_file_tree
        })
    
    except Exception as e:
        logger.error(f"Failed to scrape website: {str(e)}")
        return Response(
            {"detail": f"Failed to scrape website: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_file_content(request, file_id):
    try:
        # Get file
        file = get_object_or_404(File, id=file_id)
        
        # Check if user has access to this file
        if file.workspace.user != request.user:
            # Check if user is a team member
            team_member = TeamMember.objects.filter(
                user=request.user,
                invited_by=file.workspace.user
            ).exists()
            
            if not team_member:
                return Response(
                    {"detail": "You do not have permission to access this file"},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get file content
        try:
            content = file.content.content
        except FileContent.DoesNotExist:
            content = {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": ""}]
                    }
                ]
            }
            FileContent.objects.create(file=file, content=content)
        
        return Response({"content": content})
    
    except Exception as e:
        logger.error(f"Error retrieving file content: {str(e)}")
        return Response(
            {"detail": f"Error retrieving file content: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_content(request):
    serializer = SaveContentSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    file_id = serializer.validated_data['file_id']
    content = serializer.validated_data['content']
    
    try:
        # Get file
        file = get_object_or_404(File, id=file_id)
        
        # Check if user has access to this file
        if file.workspace.user != request.user:
            # Check if user is a team member
            team_member = TeamMember.objects.filter(
                user=request.user,
                invited_by=file.workspace.user
            ).exists()
            
            if not team_member:
                return Response(
                    {"detail": "You do not have permission to access this file"},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Update or create file content
        file_content, created = FileContent.objects.update_or_create(
            file=file,
            defaults={'content': content}
        )
        
        return Response({"message": "Content saved successfully"})
    
    except Exception as e:
        logger.error(f"Error saving file content: {str(e)}")
        return Response(
            {"detail": f"Error saving file content: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_file_by_uuid(request, file_uuid):
    try:
        # Get file
        file = get_object_or_404(File, id=file_uuid)
        
        # Check if user has access to this file
        if file.workspace.user != request.user:
            # Check if user is a team member
            team_member = TeamMember.objects.filter(
                user=request.user,
                invited_by=file.workspace.user
            ).exists()
            
            if not team_member:
                return Response(
                    {"detail": "You do not have permission to access this file"},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get file details
        file_data = {
            "id": str(file.id),
            "name": file.name,
            "type": file.type,
            "workspace": {
                "id": file.workspace.id,
                "name": file.workspace.name
            }
        }
        
        return Response(file_data)
    
    except Exception as e:
        logger.error(f"Error retrieving file: {str(e)}")
        return Response(
            {"detail": f"Error retrieving file: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_team_members(request):
    try:
        # Get team members invited by the current user
        team_members = TeamMember.objects.filter(invited_by=request.user)
        
        # Get team members who invited the current user
        invitations = TeamMember.objects.filter(user=request.user)
        
        # Combine the results
        team_data = {
            "team_members": [
                {
                    "id": member.id,
                    "email": member.user.email,
                    "name": member.user.name,
                    "created_at": member.created_at
                }
                for member in team_members
            ],
            "invitations": [
                {
                    "id": invitation.id,
                    "invited_by": {
                        "email": invitation.invited_by.email,
                        "name": invitation.invited_by.name
                    },
                    "created_at": invitation.created_at
                }
                for invitation in invitations
            ]
        }
        
        return Response(team_data)
    
    except Exception as e:
        logger.error(f"Error retrieving team members: {str(e)}")
        return Response(
            {"detail": f"Error retrieving team members: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# import json
# import uuid
# import requests
# from bs4 import BeautifulSoup
# from rest_framework import status, generics
# from rest_framework.response import Response
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.decorators import api_view, permission_classes
# from django.shortcuts import get_object_or_404
# from django.http import HttpResponse, JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from .models import Workspace, File, FileContent
# from .serializers import WorkspaceSerializer, FileSerializer, ScrapeWebsiteSerializer, SaveContentSerializer
# from users.models import TeamMember, User
# import re
# import logging
# import time
# from urllib.parse import urljoin, urlparse

# logger = logging.getLogger(__name__)

# class WorkspaceListView(generics.ListCreateAPIView):
#     serializer_class = WorkspaceSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         return Workspace.objects.filter(user=self.request.user)

#     def perform_create(self, serializer):
#         serializer.save(user=self.request.user)

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def get_workspace(request):
#     # Get user's workspace or create one
#     workspace, created = Workspace.objects.get_or_create(
#         user=request.user,
#         defaults={'name': 'My Workspace'}
#     )
    
#     # Get root folders
#     root_files = File.objects.filter(
#         workspace=workspace,
#         parent=None
#     )
    
#     # Build file tree
#     file_tree = []
#     for file in root_files:
#         file_tree.append(build_file_tree(file))
    
#     return Response({'fileTree': file_tree})

# def build_file_tree(file):
#     result = {
#         'id': str(file.id),
#         'name': file.name,
#         'type': file.type
#     }
    
#     if file.type == 'folder':
#         children = File.objects.filter(parent=file)
#         result['children'] = [build_file_tree(child) for child in children]
    
#     return result

# def html_to_tiptap_json(html_content, title=""):
#     """Convert HTML content to Tiptap JSON format with improved handling for Mixpanel docs."""
#     try:
#         # Create the base document structure
#         doc = {
#             "type": "doc",
#             "content": []
#         }
        
#         # Add title as h1 if provided
#         if title:
#             doc["content"].append({
#                 "type": "heading",
#                 "attrs": {"level": 1},
#                 "content": [{"type": "text", "text": title}]
#             })
        
#         # Parse HTML with BeautifulSoup
#         soup = BeautifulSoup(html_content, 'html.parser')
        
#         # Remove script and style elements
#         for script in soup(["script", "style"]):
#             script.decompose()
        
#         # Process each element
#         for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'li', 'a', 'img', 'code', 'pre', 'blockquote', 'div']):
#             if element.name.startswith('h') and len(element.name) == 2:
#                 # Handle headings
#                 level = int(element.name[1])
#                 heading_content = []
                
#                 # Process text and links within heading
#                 for child in element.children:
#                     if child.name == 'a':
#                         heading_content.append({
#                             "type": "text", 
#                             "text": child.get_text(),
#                             "marks": [{"type": "link", "attrs": {"href": child.get('href', '#')}}]
#                         })
#                     elif isinstance(child, str) or child.name is None:
#                         heading_content.append({"type": "text", "text": child.string or ""})
                
#                 if not heading_content:
#                     heading_content = [{"type": "text", "text": element.get_text()}]
                
#                 doc["content"].append({
#                     "type": "heading",
#                     "attrs": {"level": level},
#                     "content": heading_content
#                 })
            
#             elif element.name == 'p':
#                 # Handle paragraphs
#                 paragraph = {
#                     "type": "paragraph",
#                     "content": []
#                 }
                
#                 # Process text, links, and other inline elements
#                 for child in element.children:
#                     if child.name == 'a':
#                         paragraph["content"].append({
#                             "type": "text", 
#                             "text": child.get_text(),
#                             "marks": [{"type": "link", "attrs": {"href": child.get('href', '#')}}]
#                         })
#                     elif child.name == 'strong' or child.name == 'b':
#                         paragraph["content"].append({
#                             "type": "text", 
#                             "text": child.get_text(),
#                             "marks": [{"type": "bold"}]
#                         })
#                     elif child.name == 'em' or child.name == 'i':
#                         paragraph["content"].append({
#                             "type": "text", 
#                             "text": child.get_text(),
#                             "marks": [{"type": "italic"}]
#                         })
#                     elif child.name == 'code':
#                         paragraph["content"].append({
#                             "type": "text", 
#                             "text": child.get_text(),
#                             "marks": [{"type": "code"}]
#                         })
#                     elif isinstance(child, str) or child.name is None:
#                         if child.string and child.string.strip():
#                             paragraph["content"].append({"type": "text", "text": child.string})
                
#                 # If no content was processed, add the full text
#                 if not paragraph["content"]:
#                     paragraph["content"] = [{"type": "text", "text": element.get_text()}]
                
#                 doc["content"].append(paragraph)
            
#             elif element.name == 'ul':
#                 # Handle unordered lists
#                 list_item = {
#                     "type": "bulletList",
#                     "content": []
#                 }
#                 for li in element.find_all('li', recursive=False):
#                     list_content = {
#                         "type": "listItem",
#                         "content": [{
#                             "type": "paragraph",
#                             "content": []
#                         }]
#                     }
                    
#                     # Process text and links within list item
#                     for child in li.children:
#                         if child.name == 'a':
#                             list_content["content"][0]["content"].append({
#                                 "type": "text", 
#                                 "text": child.get_text(),
#                                 "marks": [{"type": "link", "attrs": {"href": child.get('href', '#')}}]
#                             })
#                         elif child.name == 'strong' or child.name == 'b':
#                             list_content["content"][0]["content"].append({
#                                 "type": "text", 
#                                 "text": child.get_text(),
#                                 "marks": [{"type": "bold"}]
#                             })
#                         elif isinstance(child, str) or child.name is None:
#                             if child.string and child.string.strip():
#                                 list_content["content"][0]["content"].append({"type": "text", "text": child.string})
                    
#                     # If no content was processed, add the full text
#                     if not list_content["content"][0]["content"]:
#                         list_content["content"][0]["content"] = [{"type": "text", "text": li.get_text()}]
                    
#                     list_item["content"].append(list_content)
                
#                 doc["content"].append(list_item)
            
#             elif element.name == 'ol':
#                 # Handle ordered lists
#                 list_item = {
#                     "type": "orderedList",
#                     "content": []
#                 }
#                 for li in element.find_all('li', recursive=False):
#                     list_content = {
#                         "type": "listItem",
#                         "content": [{
#                             "type": "paragraph",
#                             "content": [{"type": "text", "text": li.get_text()}]
#                         }]
#                     }
#                     list_item["content"].append(list_content)
                
#                 doc["content"].append(list_item)
            
#             elif element.name == 'blockquote':
#                 # Handle blockquotes
#                 doc["content"].append({
#                     "type": "blockquote",
#                     "content": [{
#                         "type": "paragraph",
#                         "content": [{"type": "text", "text": element.get_text()}]
#                     }]
#                 })
            
#             elif element.name == 'pre':
#                 # Handle code blocks
#                 code_content = element.get_text()
#                 language = ""
                
#                 # Try to detect language from class
#                 if element.has_attr('class'):
#                     for cls in element['class']:
#                         if cls.startswith('language-'):
#                             language = cls.replace('language-', '')
                
#                 doc["content"].append({
#                     "type": "codeBlock",
#                     "attrs": {"language": language},
#                     "content": [{"type": "text", "text": code_content}]
#                 })
            
#             elif element.name == 'img':
#                 # Handle images
#                 src = element.get('src', '')
#                 alt = element.get('alt', '')
                
#                 doc["content"].append({
#                     "type": "image",
#                     "attrs": {
#                         "src": src,
#                         "alt": alt,
#                         "title": alt
#                     }
#                 })
            
#             elif element.name == 'div' and element.get('class') and any('nextra-content' in cls for cls in element.get('class')):
#                 # Special handling for Mixpanel docs main content div
#                 for child in element.children:
#                     if child.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'blockquote', 'pre']:
#                         # Recursively process these elements
#                         child_content = html_to_tiptap_json(str(child))
#                         if child_content.get("content"):
#                             doc["content"].extend(child_content["content"])
        
#         # If no content was added, add an empty paragraph
#         if not doc["content"]:
#             doc["content"].append({
#                 "type": "paragraph",
#                 "content": [{"type": "text", "text": ""}]
#             })
        
#         return doc
#     except Exception as e:
#         logger.error(f"Error converting HTML to Tiptap JSON: {str(e)}")
#         # Return a simple document with the error
#         return {
#             "type": "doc",
#             "content": [
#                 {
#                     "type": "paragraph",
#                     "content": [{"type": "text", "text": f"Error processing content: {str(e)}"}]
#                 }
#             ]
#         }

# def extract_mixpanel_content(soup, url):
#     """Extract content specifically from Mixpanel documentation."""
#     # Try to find the main content area specific to Mixpanel docs
#     main_content = None
    
#     # Mixpanel specific content selectors
#     content_selectors = [
#         'article.nextra-content',
#         'main',
#         '.nextra-content',
#         'article',
#         '.content',
#         '#content',
#         '.main-content',
#         '#main-content'
#     ]
    
#     # Try each selector
#     for selector in content_selectors:
#         content = soup.select_one(selector)
#         if content and len(content.get_text(strip=True)) > 100:
#             main_content = content
#             break
    
#     # If no main content found, use the body
#     if not main_content:
#         main_content = soup.body
    
#     # Extract headings to create sections
#     headings = main_content.find_all(['h1', 'h2', 'h3'], recursive=True)
    
#     # If no headings found, return the whole content as one section
#     if not headings:
#         return [{
#             'title': soup.title.string if soup.title else "Untitled Document",
#             'content': str(main_content)
#         }]
    
#     # Create sections based on headings
#     sections = []
#     for i, heading in enumerate(headings):
#         title = heading.get_text(strip=True)
#         if not title:
#             title = f"Section {i+1}"
        
#         # Get content until next heading
#         content = ""
#         next_node = heading.next_sibling
        
#         # Collect all content until the next heading
#         while next_node:
#             if next_node.name in ['h1', 'h2', 'h3'] and next_node in headings:
#                 break
#             if next_node.name:
#                 content += str(next_node)
#             next_node = next_node.next_sibling
        
#         # If content is too short, it might be just a heading without content
#         if len(content.strip()) < 50:
#             # Try to get the parent container
#             parent = heading.parent
#             if parent and parent.name not in ['body', 'html']:
#                 # Get all siblings after the heading until the next heading
#                 siblings_content = ""
#                 sibling = heading.next_sibling
#                 while sibling:
#                     if sibling.name in ['h1', 'h2', 'h3'] and sibling in headings:
#                         break
#                     if sibling.name:
#                         siblings_content += str(sibling)
#                     sibling = sibling.next_sibling
                
#                 if len(siblings_content.strip()) > 50:
#                     content = siblings_content
#                 else:
#                     # Use the parent content as fallback
#                     content = str(parent)
        
#         sections.append({
#             'title': title,
#             'content': f"<{heading.name}>{title}</{heading.name}>{content}"
#         })
    
#     return sections

# def extract_mixpanel_links(soup, base_url):
#     """Extract navigation links from Mixpanel documentation."""
#     links = []
    
#     # Find navigation links in the sidebar
#     nav_links = soup.select('.nextra-sidebar-container a')
    
#     for link in nav_links:
#         href = link.get('href')
#         if href and not href.startswith('#'):
#             # Handle relative URLs
#             if not href.startswith('http'):
#                 href = urljoin(base_url, href)
            
#             # Only include Mixpanel docs links
#             if 'docs.mixpanel.com' in href:
#                 links.append({
#                     'url': href,
#                     'text': link.get_text(strip=True)
#                 })
    
#     return links

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def scrape_website(request):
#     serializer = ScrapeWebsiteSerializer(data=request.data)
#     if not serializer.is_valid():
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     url = serializer.validated_data['url']
    
#     # Check if URL is from Mixpanel docs
#     is_mixpanel_docs = 'docs.mixpanel.com' in url
    
#     try:
#         # Fetch the website content
#         headers = {
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
#         }
#         response = requests.get(url, headers=headers, timeout=30)
#         response.raise_for_status()
        
#         # Parse HTML with BeautifulSoup
#         soup = BeautifulSoup(response.text, 'html.parser')
        
#         # Extract title
#         title = soup.title.string if soup.title else "Untitled Document"
        
#         # Get or create workspace
#         workspace, created = Workspace.objects.get_or_create(
#             user=request.user,
#             defaults={'name': 'My Workspace'}
#         )
        
#         # Create a root folder for the scraped content
#         root_folder = File.objects.create(
#             workspace=workspace,
#             name=title,
#             type='folder',
#             parent=None
#         )
        
#         # Extract content sections based on whether it's Mixpanel docs or not
#         if is_mixpanel_docs:
#             sections = extract_mixpanel_content(soup, url)
#             # Extract navigation links for potential further scraping
#             nav_links = extract_mixpanel_links(soup, url)
            
#             # Create a file to store navigation links
#             nav_file = File.objects.create(
#                 workspace=workspace,
#                 name="Navigation Links",
#                 type='file',
#                 parent=root_folder
#             )
            
#             # Convert links to Tiptap JSON
#             nav_content = {
#                 "type": "doc",
#                 "content": [
#                     {
#                         "type": "heading",
#                         "attrs": {"level": 1},
#                         "content": [{"type": "text", "text": "Navigation Links"}]
#                     },
#                     {
#                         "type": "paragraph",
#                         "content": [{"type": "text", "text": "Links extracted from the Mixpanel documentation:"}]
#                     },
#                     {
#                         "type": "bulletList",
#                         "content": []
#                     }
#                 ]
#             }
            
#             for link in nav_links:
#                 nav_content["content"][2]["content"].append({
#                     "type": "listItem",
#                     "content": [{
#                         "type": "paragraph",
#                         "content": [{
#                             "type": "text",
#                             "text": link['text'],
#                             "marks": [{"type": "link", "attrs": {"href": link['url']}}]
#                         }]
#                     }]
#                 })
            
#             # Create file content for navigation links
#             FileContent.objects.create(
#                 file=nav_file,
#                 content=nav_content
#             )
#         else:
#             # Use the original extraction method for non-Mixpanel sites
#             sections = extract_content_sections(soup, url)
        
#         file_tree = []
        
#         for section in sections:
#             section_title = section['title']
#             section_content = section['content']
            
#             # Create file in database
#             file = File.objects.create(
#                 workspace=workspace,
#                 name=section_title,
#                 type='file',
#                 parent=root_folder
#             )
            
#             # Convert HTML to Tiptap JSON
#             tiptap_content = html_to_tiptap_json(section_content, section_title)
            
#             # Create file content
#             file_content = FileContent.objects.create(
#                 file=file,
#                 content=tiptap_content
#             )
            
#             # Add to file tree
#             file_tree.append({
#                 "id": str(file.id),
#                 "name": section_title,
#                 "type": "file"
#             })
        
#         # Build complete file tree
#         complete_file_tree = [{
#             "id": str(root_folder.id),
#             "name": root_folder.name,
#             "type": "folder",
#             "children": file_tree
#         }]
        
#         return Response({
#             "message": "Website scraped successfully", 
#             "fileTree": complete_file_tree
#         })
    
#     except Exception as e:
#         logger.error(f"Failed to scrape website: {str(e)}")
#         return Response(
#             {"detail": f"Failed to scrape website: {str(e)}"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def scrape_mixpanel_docs(request):
#     """Specialized endpoint for scraping Mixpanel documentation."""
#     serializer = ScrapeWebsiteSerializer(data=request.data)
#     if not serializer.is_valid():
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     url = serializer.validated_data['url']
#     max_pages = serializer.validated_data.get('max_pages', 5)  # Default to 5 pages
    
#     # Validate URL is from Mixpanel docs
#     if 'docs.mixpanel.com' not in url:
#         return Response(
#             {"detail": "URL must be from Mixpanel documentation (docs.mixpanel.com)"},
#             status=status.HTTP_400_BAD_REQUEST
#         )
    
#     try:
#         # Get or create workspace
#         workspace, created = Workspace.objects.get_or_create(
#             user=request.user,
#             defaults={'name': 'My Workspace'}
#         )
        
#         # Create a root folder for the Mixpanel docs
#         root_folder = File.objects.create(
#             workspace=workspace,
#             name="Mixpanel Documentation",
#             type='folder',
#             parent=None
#         )
        
#         # Initialize variables for crawling
#         visited_urls = set()
#         urls_to_visit = [url]
#         file_tree = []
#         page_count = 0
        
#         # Crawl pages
#         while urls_to_visit and page_count < max_pages:
#             current_url = urls_to_visit.pop(0)
            
#             if current_url in visited_urls:
#                 continue
                
#             visited_urls.add(current_url)
#             page_count += 1
            
#             logger.info(f"Scraping page {page_count}/{max_pages}: {current_url}")
            
#             # Fetch the website content
#             headers = {
#                 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
#             }
#             response = requests.get(current_url, headers=headers, timeout=30)
#             response.raise_for_status()
            
#             # Parse HTML with BeautifulSoup
#             soup = BeautifulSoup(response.text, 'html.parser')
            
#             # Extract title
#             title = soup.title.string if soup.title else f"Page {page_count}"
            
#             # Create a folder for this page
#             page_folder = File.objects.create(
#                 workspace=workspace,
#                 name=title,
#                 type='folder',
#                 parent=root_folder
#             )
            
#             # Extract content sections
#             sections = extract_mixpanel_content(soup, current_url)
            
#             # Extract navigation links for further scraping
#             nav_links = extract_mixpanel_links(soup, current_url)
            
#             # Add new URLs to visit
#             for link in nav_links:
#                 if link['url'] not in visited_urls and 'docs.mixpanel.com' in link['url']:
#                     urls_to_visit.append(link['url'])
            
#             # Create files for each section
#             section_files = []
#             for section in sections:
#                 section_title = section['title']
#                 section_content = section['content']
                
#                 # Create file in database
#                 file = File.objects.create(
#                     workspace=workspace,
#                     name=section_title,
#                     type='file',
#                     parent=page_folder
#                 )
                
#                 # Convert HTML to Tiptap JSON
#                 tiptap_content = html_to_tiptap_json(section_content, section_title)
                
#                 # Create file content
#                 file_content = FileContent.objects.create(
#                     file=file,
#                     content=tiptap_content
#                 )
                
#                 # Add to section files
#                 section_files.append({
#                     "id": str(file.id),
#                     "name": section_title,
#                     "type": "file"
#                 })
            
#             # Add page folder to file tree
#             file_tree.append({
#                 "id": str(page_folder.id),
#                 "name": title,
#                 "type": "folder",
#                 "children": section_files,
#                 "url": current_url
#             })
            
#             # Add a small delay to avoid overwhelming the server
#             time.sleep(1)
        
#         # Build complete file tree
#         complete_file_tree = [{
#             "id": str(root_folder.id),
#             "name": root_folder.name,
#             "type": "folder",
#             "children": file_tree
#         }]
        
#         return Response({
#             "message": f"Successfully scraped {page_count} pages from Mixpanel documentation", 
#             "fileTree": complete_file_tree,
#             "scrapedPages": list(visited_urls)
#         })
    
#     except Exception as e:
#         logger.error(f"Failed to scrape Mixpanel docs: {str(e)}")
#         return Response(
#             {"detail": f"Failed to scrape Mixpanel docs: {str(e)}"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

# def extract_content_sections(soup, url):
#     """Extract content sections from the soup object."""
#     # Try to find the main content area
#     main_content = None
    
#     # Common content selectors
#     content_selectors = [
#         'main', 'article', '.content', '#content', '.main-content', '#main-content',
#         '.post-content', '.entry-content', '.article-content'
#     ]
    
#     # Try each selector
#     for selector in content_selectors:
#         content = soup.select_one(selector)
#         if content and len(content.get_text(strip=True)) > 100:
#             main_content = content
#             break
    
#     # If no main content found, use the body
#     if not main_content:
#         main_content = soup.body
    
#     # Extract headings to create sections
#     headings = main_content.find_all(['h1', 'h2', 'h3', 'h4'], recursive=True)
    
#     # If no headings found, return the whole content as one section
#     if not headings:
#         return [{
#             'title': soup.title.string if soup.title else "Untitled Document",
#             'content': str(main_content)
#         }]
    
#     # Create sections based on headings
#     sections = []
#     for i, heading in enumerate(headings):
#         title = heading.get_text(strip=True)
#         if not title:
#             title = f"Section {i+1}"
        
#         # Get content until next heading
#         content = ""
#         next_node = heading.next_sibling
        
#         # Collect all content until the next heading
#         while next_node:
#             if next_node.name in ['h1', 'h2', 'h3', 'h4'] and next_node in headings:
#                 break
#             if next_node.name:
#                 content += str(next_node)
#             next_node = next_node.next_sibling
        
#         # If content is too short, it might be just a heading without content
#         if len(content.strip()) < 50:
#             # Try to get the parent container
#             parent = heading.parent
#             if parent and parent.name not in ['body', 'html']:
#                 content = str(parent)
        
#         sections.append({
#             'title': title,
#             'content': f"<{heading.name}>{title}</{heading.name}>{content}"
#         })
    
#     return sections

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def get_file_content(request, file_id):
#     try:
#         # Get file
#         file = get_object_or_404(File, id=file_id)
        
#         # Check if user has access to this file
#         if file.workspace.user != request.user:
#             # Check if user is a team member
#             team_member = TeamMember.objects.filter(
#                 user=request.user,
#                 invited_by=file.workspace.user
#             ).exists()
            
#             if not team_member:
#                 return Response(
#                     {"detail": "You do not have permission to access this file"},
#                     status=status.HTTP_403_FORBIDDEN
#                 )
        
#         # Get file content
#         try:
#             content = file.content.content
#         except FileContent.DoesNotExist:
#             content = {
#                 "type": "doc",
#                 "content": [
#                     {
#                         "type": "paragraph",
#                         "content": [{"type": "text", "text": ""}]
#                     }
#                 ]
#             }
#             FileContent.objects.create(file=file, content=content)
        
#         return Response({"content": content})
    
#     except Exception as e:
#         logger.error(f"Error retrieving file content: {str(e)}")
#         return Response(
#             {"detail": f"Error retrieving file content: {str(e)}"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def save_content(request):
#     serializer = SaveContentSerializer(data=request.data)
#     if not serializer.is_valid():
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
#     file_id = serializer.validated_data['file_id']
#     content = serializer.validated_data['content']
    
#     try:
#         # Get file
#         file = get_object_or_404(File, id=file_id)
        
#         # Check if user has access to this file
#         if file.workspace.user != request.user:
#             # Check if user is a team member
#             team_member = TeamMember.objects.filter(
#                 user=request.user,
#                 invited_by=file.workspace.user
#             ).exists()
            
#             if not team_member:
#                 return Response(
#                     {"detail": "You do not have permission to access this file"},
#                     status=status.HTTP_403_FORBIDDEN
#                 )
        
#         # Update or create file content
#         file_content, created = FileContent.objects.update_or_create(
#             file=file,
#             defaults={'content': content}
#         )
        
#         return Response({"message": "Content saved successfully"})
    
#     except Exception as e:
#         logger.error(f"Error saving file content: {str(e)}")
#         return Response(
#             {"detail": f"Error saving file content: {str(e)}"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def get_file_by_uuid(request, file_uuid):
#     try:
#         # Get file
#         file = get_object_or_404(File, id=file_uuid)
        
#         # Check if user has access to this file
#         if file.workspace.user != request.user:
#             # Check if user is a team member
#             team_member = TeamMember.objects.filter(
#                 user=request.user,
#                 invited_by=file.workspace.user
#             ).exists()
            
#             if not team_member:
#                 return Response(
#                     {"detail": "You do not have permission to access this file"},
#                     status=status.HTTP_403_FORBIDDEN
#                 )
        
#         # Get file details
#         file_data = {
#             "id": str(file.id),
#             "name": file.name,
#             "type": file.type,
#             "workspace": {
#                 "id": file.workspace.id,
#                 "name": file.workspace.name
#             }
#         }
        
#         return Response(file_data)
    
#     except Exception as e:
#         logger.error(f"Error retrieving file: {str(e)}")
#         return Response(
#             {"detail": f"Error retrieving file: {str(e)}"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def get_team_members(request):
#     try:
#         # Get team members invited by the current user
#         team_members = TeamMember.objects.filter(invited_by=request.user)
        
#         # Get team members who invited the current user
#         invitations = TeamMember.objects.filter(user=request.user)
        
#         # Combine the results
#         team_data = {
#             "team_members": [
#                 {
#                     "id": member.id,
#                     "email": member.user.email,
#                     "name": member.user.name,
#                     "created_at": member.created_at
#                 }
#                 for member in team_members
#             ],
#             "invitations": [
#                 {
#                     "id": invitation.id,
#                     "invited_by": {
#                         "email": invitation.invited_by.email,
#                         "name": invitation.invited_by.name
#                     },
#                     "created_at": invitation.created_at
#                 }
#                 for invitation in invitations
#             ]
#         }
        
#         return Response(team_data)
    
#     except Exception as e:
#         logger.error(f"Error retrieving team members: {str(e)}")
#         return Response(
#             {"detail": f"Error retrieving team members: {str(e)}"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )