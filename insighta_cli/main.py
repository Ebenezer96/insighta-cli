import json
from pathlib import Path

import requests
import typer
from rich.console import Console
from rich.table import Table


app = typer.Typer(help="Insighta Labs+ CLI")
console = Console()

BASE_URL = "http://127.0.0.1:8000/api/v1"

CREDENTIALS_DIR = Path.home() / ".insighta"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"


def save_credentials(data):
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_credentials():
    if not CREDENTIALS_FILE.exists():
        console.print("[red]Not logged in. Run login first.[/red]")
        raise typer.Exit(code=1)

    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def refresh_access_token():
    credentials = load_credentials()
    refresh_token = credentials.get("refresh_token")

    if not refresh_token:
        console.print("[red]Refresh token missing. Please login again.[/red]")
        raise typer.Exit(code=1)

    response = requests.post(
        f"{BASE_URL}/auth/token/refresh/",
        json={"refresh_token": refresh_token},
        timeout=15,
    )

    if response.status_code != 200:
        console.print("[red]Token refresh failed. Please login again.[/red]")
        console.print(response.text)
        raise typer.Exit(code=1)

    data = response.json()["data"]

    new_credentials = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "token_type": "Bearer",
        "base_url": BASE_URL,
    }

    save_credentials(new_credentials)

    return data["access_token"]


def auth_headers():
    credentials = load_credentials()
    access_token = credentials.get("access_token")

    if not access_token:
        console.print("[red]Access token missing. Please login again.[/red]")
        raise typer.Exit(code=1)

    return {"Authorization": f"Bearer {access_token}"}


def authenticated_request(method, endpoint, **kwargs):
    url = f"{BASE_URL}{endpoint}"

    response = requests.request(
        method,
        url,
        headers=auth_headers(),
        timeout=15,
        **kwargs,
    )

    if response.status_code == 401:
        console.print("[yellow]Access token expired. Refreshing token...[/yellow]")

        new_access_token = refresh_access_token()

        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {new_access_token}"},
            timeout=15,
            **kwargs,
        )

    return response


@app.command()
def login():
    """
    Save access and refresh tokens after GitHub OAuth login.
    """

    console.print("[yellow]Open this URL in your browser:[/yellow]")
    console.print(f"{BASE_URL}/auth/github/login/")
    console.print()

    access_token = typer.prompt("Paste access_token")
    refresh_token = typer.prompt("Paste refresh_token")

    save_credentials(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "base_url": BASE_URL,
        }
    )

    console.print("[green]Login successful. Credentials saved to ~/.insighta/credentials.json[/green]")


@app.command()
def refresh():
    """
    Manually refresh access token.
    """

    refresh_access_token()
    console.print("[green]Token refreshed successfully.[/green]")


@app.command()
def profiles(
    gender: str = typer.Option(None, help="Filter by gender"),
    age_group: str = typer.Option(None, help="Filter by age group"),
    country_id: str = typer.Option(None, help="Filter by country code"),
    page: int = typer.Option(1, help="Page number"),
    limit: int = typer.Option(10, help="Items per page"),
):
    """
    List profiles.
    """

    params = {
        "page": page,
        "limit": limit,
    }

    if gender:
        params["gender"] = gender

    if age_group:
        params["age_group"] = age_group

    if country_id:
        params["country_id"] = country_id

    response = authenticated_request(
        "GET",
        "/profiles/",
        params=params,
    )

    if response.status_code != 200:
        console.print("[red]Request failed[/red]")
        console.print(response.text)
        raise typer.Exit(code=1)

    payload = response.json()
    data = payload.get("data", [])
    pagination = payload.get("pagination", {})

    table = Table(title="Profiles")
    table.add_column("Name")
    table.add_column("Gender")
    table.add_column("Age")
    table.add_column("Age Group")
    table.add_column("Country")
    table.add_column("Probability")

    for profile in data:
        table.add_row(
            str(profile.get("name", "")),
            str(profile.get("gender", "")),
            str(profile.get("age", "")),
            str(profile.get("age_group", "")),
            str(profile.get("country_name", "")),
            str(profile.get("country_probability", "")),
        )

    console.print(table)
    console.print(
        f"[blue]Page {pagination.get('page')} of {pagination.get('pages')} | "
        f"Total: {pagination.get('total')}[/blue]"
    )


@app.command()
def search(
    q: str = typer.Argument(..., help="Natural language search query"),
    page: int = typer.Option(1),
    limit: int = typer.Option(10),
):
    """
    Search profiles using natural language.
    """

    response = authenticated_request(
        "GET",
        "/profiles/search/",
        params={
            "q": q,
            "page": page,
            "limit": limit,
        },
    )

    if response.status_code != 200:
        console.print("[red]Search failed[/red]")
        console.print(response.text)
        raise typer.Exit(code=1)

    payload = response.json()
    data = payload.get("data", [])

    table = Table(title=f"Search Results: {q}")
    table.add_column("Name")
    table.add_column("Gender")
    table.add_column("Age")
    table.add_column("Age Group")
    table.add_column("Country")

    for profile in data:
        table.add_row(
            str(profile.get("name", "")),
            str(profile.get("gender", "")),
            str(profile.get("age", "")),
            str(profile.get("age_group", "")),
            str(profile.get("country_name", "")),
        )

    console.print(table)


@app.command()
def export(output: str = typer.Option("profiles.csv", help="Output CSV file")):
    """
    Export profiles as CSV. Admin only.
    """

    response = authenticated_request(
        "GET",
        "/profiles/export/",
    )

    if response.status_code == 403:
        console.print("[red]Forbidden: admin role required.[/red]")
        raise typer.Exit(code=1)

    if response.status_code != 200:
        console.print("[red]Export failed[/red]")
        console.print(response.text)
        raise typer.Exit(code=1)

    with open(output, "wb") as file:
        file.write(response.content)

    console.print(f"[green]Profiles exported to {output}[/green]")


@app.command()
def logout():
    """
    Remove stored credentials.
    """

    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()

    console.print("[green]Logged out successfully.[/green]")


if __name__ == "__main__":
    app()