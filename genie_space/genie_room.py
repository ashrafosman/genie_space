import pandas as pd
import time
import requests
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import backoff
import uuid
from token_minter import TokenMinter
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Load environment variables
SPACE_ID = os.environ.get("SPACE_ID")
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST")
CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET")

token_minter = TokenMinter(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    host=DATABRICKS_HOST
)


class GenieClient:
    def __init__(self, host: str, space_id: str, user_token: str = None):
        self.host = host
        self.space_id = space_id
        self.user_token = user_token
        self.update_headers()
        
        self.base_url = f"https://{host}/api/2.0/genie/spaces/{space_id}"
    
    def update_headers(self, use_service_principal: bool = False, add_user_context: bool = False) -> None:
        """Update headers with user token by default, service principal token only when specified"""
        if not use_service_principal and self.user_token:
            logger.info(f"Using user token for query execution (token length: {len(self.user_token)})")
            access_token = self.user_token
        else:
            logger.info("Using service principal token for API call")
            access_token = token_minter.get_token()
            
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Add user context headers if requested and user token is available
        if add_user_context and self.user_token:
            try:
                import base64
                import json
                parts = self.user_token.split('.')
                if len(parts) >= 2:
                    payload_part = parts[1]
                    payload_part += '=' * (4 - len(payload_part) % 4)
                    decoded = base64.b64decode(payload_part)
                    token_data = json.loads(decoded)
                    
                    # Look for user identifier in JWT
                    user_id = token_data.get('sub') or token_data.get('email') or token_data.get('preferred_username')
                    if user_id:
                        self.headers["X-Databricks-User-Context"] = user_id
                        self.headers["X-User-Context"] = user_id
                        logger.info(f"Adding user context headers: {user_id}")
            except Exception as e:
                logger.warning(f"Could not extract user context for headers: {e}")
    
    @backoff.on_exception(
        backoff.expo,
        Exception,  
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def start_conversation(self, question: str) -> Dict[str, Any]:
        """Start a new conversation with the given question using user token only.

        Raises:
            PermissionError: If user token is missing or lacks required scopes/permissions
        """
        url = f"{self.base_url}/start-conversation"
        payload = {"content": question}

        if not self.user_token:
            error_msg = "User token is required to start a conversation. Please log in."
            logger.error(error_msg)
            raise PermissionError(error_msg)

        logger.info(f"Using user credentials for start-conversation. URL: {url}")
        logger.info(f"User token length: {len(self.user_token)}")
        self.update_headers(use_service_principal=False)
        logger.info(f"Request headers: {self.headers}")
        logger.info(f"Request payload: {payload}")

        response = requests.post(url, headers=self.headers, json=payload)
        logger.info(f"User token response status: {response.status_code}")

        if response.status_code == 403:
            error_response = response.text.strip()
            if "Invalid scope" in error_response:
                error_msg = (
                    "Authentication Error: Invalid token scope.\n\n"
                    "The provided token doesn't have the required permissions to start a conversation.\n"
                    "Ensure your Databricks access token includes the necessary OAuth scopes and try again."
                )
            else:
                error_msg = (
                    "Permission denied. Your account doesn't have the necessary permissions to start a conversation.\n"
                    "Please verify your Databricks permissions or contact your administrator."
                )
            logger.error(f"Permission denied. Status: {response.status_code}, Response: {error_response}")
            raise PermissionError(error_msg)

        response.raise_for_status()
        return response.json()
    
    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def send_message(self, conversation_id: str, message: str) -> Dict[str, Any]:
        """Send a follow-up message to an existing conversation using user token only."""
        if not self.user_token:
            error_msg = "User token is required to send a message. Please log in."
            logger.error(error_msg)
            raise PermissionError(error_msg)

        self.update_headers(use_service_principal=False)
        url = f"{self.base_url}/conversations/{conversation_id}/messages"
        payload = {"content": message}

        response = requests.post(url, headers=self.headers, json=payload)

        if response.status_code == 403:
            error_response = response.text.strip()
            if "Invalid scope" in error_response:
                error_msg = (
                    "Authentication Error: Invalid token scope.\n\n"
                    "The provided token doesn't have the required permissions to send messages.\n"
                    "Ensure your Databricks access token includes the necessary OAuth scopes and try again."
                )
            else:
                error_msg = (
                    "Permission denied. Your account doesn't have the necessary permissions to send messages.\n"
                    "Please verify your Databricks permissions or contact your administrator."
                )
            logger.error(f"Permission denied. Status: {response.status_code}, Response: {error_response}")
            raise PermissionError(error_msg)

        response.raise_for_status()
        return response.json()

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def get_message(self, conversation_id: str, message_id: str) -> Dict[str, Any]:
        """Get the details of a specific message using user token only."""
        if not self.user_token:
            error_msg = "User token is required to get message details. Please log in."
            logger.error(error_msg)
            raise PermissionError(error_msg)

        self.update_headers(use_service_principal=False)
        url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}"

        response = requests.get(url, headers=self.headers)

        if response.status_code == 403:
            error_response = response.text.strip()
            if "Invalid scope" in error_response:
                error_msg = (
                    "Authentication Error: Invalid token scope.\n\n"
                    "The provided token doesn't have the required permissions to view message details.\n"
                    "Ensure your Databricks access token includes the necessary OAuth scopes and try again."
                )
            else:
                error_msg = (
                    "Permission denied. Your account doesn't have the necessary permissions to view message details.\n"
                    "Please verify your Databricks permissions or contact your administrator."
                )
            logger.error(f"Permission denied. Status: {response.status_code}, Response: {error_response}")
            raise PermissionError(error_msg)

        response.raise_for_status()
        return response.json()

    def get_query_result(self, conversation_id: str, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """Get the query result using the attachment_id endpoint with user token only
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            attachment_id: The ID of the attachment containing the query result
            
        Returns:
            Dict containing the query result
            
        Raises:
            PermissionError: If user token is missing or doesn't have required permissions
            Exception: For other types of errors
        """
        query_result_url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
        
        logger.info(f"Attempting to get query result from: {query_result_url}")
        
        if not self.user_token:
            error_msg = "User token is required to fetch query results. Please log in."
            logger.error(error_msg)
            raise PermissionError(error_msg)
            
        logger.info("Using user token for query-result")
        self.update_headers(use_service_principal=False)
        
        try:
            response = requests.get(query_result_url, headers=self.headers)
            
            if response.status_code == 403:
                error_response = response.text.strip()
                if 'Invalid scope' in error_response:
                    error_msg = """
                    Authentication Error: Invalid token scope.
                    
                    The provided token doesn't have the required permissions to access query results.
                    This usually happens when the token is missing necessary OAuth scopes.
                    
                    Please ensure you're using a valid Databricks access token with the correct scopes.
                    You may need to re-authenticate with the necessary permissions.
                    """
                else:
                    error_msg = """
                    Permission denied. Your account doesn't have the necessary permissions to view query results.
                    Please ensure you have the correct Databricks permissions and try again.
                    
                    If you believe this is an error, please contact your Databricks administrator.
                    """
                logger.error(f"Permission denied. Status: {response.status_code}, Response: {error_response}")
                raise PermissionError(error_msg.strip())
                
            response.raise_for_status()  # This will raise for other 4XX/5XX errors
            
            result = response.json()
            
            # Extract data_array from the correct nested location
            data_array = []
            if 'statement_response' in result:
                if 'result' in result['statement_response']:
                    data_array = result['statement_response']['result'].get('data_array', [])
                
            return {
                'data_array': data_array,
                'schema': result.get('statement_response', {}).get('manifest', {}).get('schema', {})
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching query result: {str(e)}")
            raise Exception(f"Failed to fetch query result: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def execute_query(self, conversation_id: str, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """Execute a query using the attachment_id endpoint with user token only
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            attachment_id: The ID of the attachment containing the query
            
        Returns:
            Dict containing the query execution result
            
        Raises:
            PermissionError: If user token is missing or doesn't have required permissions
            Exception: For other types of errors
        """
        url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/execute-query"
        
        logger.info(f"Executing query at: {url}")
        
        if not self.user_token:
            error_msg = "User token is required to execute queries. Please log in."
            logger.error(error_msg)
            raise PermissionError(error_msg)
            
        logger.info("Using user token for execute-query")
        self.update_headers(use_service_principal=False)
        
        try:
            response = requests.post(url, headers=self.headers)
            
            if response.status_code == 403:
                error_response = response.text.strip()
                if 'Invalid scope' in error_response:
                    error_msg = """
                    Authentication Error: Invalid token scope.
                    
                    The provided token doesn't have the required permissions to execute queries.
                    This usually happens when the token is missing necessary OAuth scopes.
                    
                    Please ensure you're using a valid Databricks access token with the correct scopes.
                    You may need to re-authenticate with the necessary permissions.
                    """
                else:
                    error_msg = """
                    Permission denied. Your account doesn't have the necessary permissions to execute queries.
                    Please ensure you have the correct Databricks permissions and try again.
                    
                    If you believe this is an error, please contact your Databricks administrator.
                    """
                logger.error(f"Permission denied. Status: {response.status_code}, Response: {error_response}")
                raise PermissionError(error_msg.strip())
                
            response.raise_for_status()  # This will raise for other 4XX/5XX errors
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error executing query: {str(e)}")
            raise Exception(f"Failed to execute query: {str(e)}")
    

    def wait_for_message_completion(self, conversation_id: str, message_id: str, timeout: int = 300, poll_interval: int = 2) -> Dict[str, Any]:
        """
        Wait for a message to reach a terminal state (COMPLETED, ERROR, etc.).
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            
        Returns:
            The completed message
        """
        
        start_time = time.time()
        attempt = 1
        
        while time.time() - start_time < timeout:
            
            message = self.get_message(conversation_id, message_id)
            status = message.get("status")
            
            if status in ["COMPLETED", "ERROR", "FAILED"]:
                return message
                
            time.sleep(poll_interval)
            attempt += 1
            
        raise TimeoutError(f"Message processing timed out after {timeout} seconds")

def start_new_conversation(question: str, user_token: str = None) -> Tuple[str, Union[str, pd.DataFrame], Optional[str]]:
    """
    Start a new conversation with Genie.
    
    Args:
        question: The initial question
        user_token: User access token from X-Forwarded-Access-Token header
        
    Returns:
        Tuple containing:
        - conversation_id: The new conversation ID
        - response: Either text or DataFrame response
        - query_text: SQL query text if applicable, otherwise None
    """
    import logging
    logging.info(f"User token received: {user_token}")
    
    client = GenieClient(
        host=DATABRICKS_HOST,
        space_id=SPACE_ID,
        user_token=user_token
    )
    
    try:
        # Start a new conversation
        response = client.start_conversation(question)
        conversation_id = response.get("conversation_id")
        message_id = response.get("message_id")
        
        # Wait for the message to complete
        complete_message = client.wait_for_message_completion(conversation_id, message_id)
        
        # Process the response
        result, query_text = process_genie_response(client, conversation_id, message_id, complete_message)
        
        return conversation_id, result, query_text
        
    except Exception as e:
        return None, f"Sorry, an error occurred: {str(e)}. Please try again.", None

def continue_conversation(conversation_id: str, question: str, user_token: str = None) -> Tuple[Union[str, pd.DataFrame], Optional[str]]:
    """
    Send a follow-up message in an existing conversation.
    
    Args:
        conversation_id: The existing conversation ID
        question: The follow-up question
        user_token: User access token from X-Forwarded-Access-Token header
        
    Returns:
        Tuple containing:
        - response: Either text or DataFrame response
        - query_text: SQL query text if applicable, otherwise None
    """
    logger.info(f"Continuing conversation {conversation_id} with question: {question[:30]}...")
    
    client = GenieClient(
        host=DATABRICKS_HOST,
        space_id=SPACE_ID,
        user_token=user_token
    )
    
    try:
        # Send follow-up message in existing conversation
        response = client.send_message(conversation_id, question)
        message_id = response.get("message_id")
        
        # Wait for the message to complete
        complete_message = client.wait_for_message_completion(conversation_id, message_id)
        
        # Process the response
        result, query_text = process_genie_response(client, conversation_id, message_id, complete_message)
        
        return result, query_text
        
    except Exception as e:
        # Handle specific errors
        if "429" in str(e) or "Too Many Requests" in str(e):
            return "Sorry, the system is currently experiencing high demand. Please try again in a few moments.", None
        elif "Conversation not found" in str(e):
            return "Sorry, the previous conversation has expired. Please try your query again to start a new conversation.", None
        else:
            logger.error(f"Error continuing conversation: {str(e)}")
            return f"Sorry, an error occurred: {str(e)}", None

def process_genie_response(client, conversation_id, message_id, complete_message) -> Tuple[Union[str, pd.DataFrame], Optional[str]]:
    """
    Process the response from Genie
    
    Args:
        client: The GenieClient instance
        conversation_id: The conversation ID
        message_id: The message ID
        complete_message: The completed message response
        
    Returns:
        Tuple containing:
        - result: Either text or DataFrame response
        - query_text: SQL query text if applicable, otherwise None
    """
    # Check attachments first
    attachments = complete_message.get("attachments", [])
    for attachment in attachments:
        attachment_id = attachment.get("attachment_id")
        
        # If there's text content in the attachment, return it
        if "text" in attachment and "content" in attachment["text"]:
            return attachment["text"]["content"], None
        
        # If there's a query, get the result
        elif "query" in attachment:
            query_text = attachment.get("query", {}).get("query", "")
            query_result = client.get_query_result(conversation_id, message_id, attachment_id)
           
            data_array = query_result.get('data_array', [])
            schema = query_result.get('schema', {})
            columns = [col.get('name') for col in schema.get('columns', [])]
            
            # If we have data, return as DataFrame
            if data_array:
                # If no columns from schema, create generic ones
                if not columns and data_array and len(data_array) > 0:
                    columns = [f"column_{i}" for i in range(len(data_array[0]))]
                
                df = pd.DataFrame(data_array, columns=columns)
                return df, query_text
    
    # If no attachments or no data in attachments, return text content
    if 'content' in complete_message:
        return complete_message.get('content', ''), None
    
    return "No response available", None

def genie_query(question: str, user_token: str = None) -> Union[Tuple[str, Optional[str]], Tuple[pd.DataFrame, str]]:
    """
    Main entry point for querying Genie.
    
    Args:
        question: The question to ask
        user_token: User access token from X-Forwarded-Access-Token header
        
    Returns:
        Tuple containing either:
        - (text_response, None) for text responses
        - (dataframe, sql_query) for data responses
    """
    try:
        # Start a new conversation for each query
        conversation_id, result, query_text = start_new_conversation(question, user_token)
        return result, query_text
            
    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}. Please try again.")
        return f"Sorry, an error occurred: {str(e)}. Please try again.", None

