import { GraphQLClient } from 'graphql-request'

const endpoint =
  process.env.NEXT_PUBLIC_GRAPHQL_URL ?? 'http://localhost:8000/graphql'

export const gqlClient = new GraphQLClient(endpoint)
