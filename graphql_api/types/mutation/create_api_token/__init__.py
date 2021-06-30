from graphql_api.helpers.ariadne import ariadne_load_local_graphql

from .create_api_token import resolve_create_api_token, error_create_api_token


gql_create_api_token = ariadne_load_local_graphql(__file__, "create_api_token.graphql")
