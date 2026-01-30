"""Asynchronous operations example.

This example demonstrates how to perform concurrent operations
using the asynchronous client.
"""

import asyncio

from py_strapi import AsyncClient, StrapiConfig


async def main() -> None:
    """Demonstrate async operations with concurrent requests."""
    # Configure client
    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="your-api-token-here",
    )

    # Use async client with context manager
    async with AsyncClient(config) as client:
        print("Connected to Strapi (async)")
        print(f"API Version: {client.api_version or 'auto-detecting...'}")

        # Sequential requests
        print("\n1. Sequential requests...")
        try:
            articles = await client.get("articles", params={"pagination[limit]": 5})
            print(f"Articles: {len(articles.get('data', []))}")

            categories = await client.get("categories", params={"pagination[limit]": 5})
            print(f"Categories: {len(categories.get('data', []))}")
        except Exception as e:
            print(f"Error: {e}")

        # Concurrent requests - much faster!
        print("\n2. Concurrent requests...")
        try:
            tasks = [
                client.get("articles", params={"pagination[limit]": 5}),
                client.get("categories", params={"pagination[limit]": 5}),
                client.get("tags", params={"pagination[limit]": 5}),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Request {i + 1} failed: {result}")
                else:
                    print(f"Request {i + 1}: {len(result.get('data', []))} items")
        except Exception as e:
            print(f"Error: {e}")

        # Batch create operations
        print("\n3. Batch create articles...")
        try:
            create_tasks = []
            for i in range(3):
                article_data = {
                    "data": {
                        "title": f"Async Article {i + 1}",
                        "content": f"Content for article {i + 1}",
                    }
                }
                create_tasks.append(client.post("articles", json=article_data))

            created = await asyncio.gather(*create_tasks, return_exceptions=True)

            successful = sum(1 for r in created if not isinstance(r, Exception))
            print(f"Created {successful} articles")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
