"""\
GLO-2000 Travail pratique 4 - Client
Noms et numéros étudiants:
- Raphaël Chheang 536 993 135
- Loïc Boutet 536 981 506
-
"""

import argparse
import getpass
import json
import socket
import sys

import glosocket
import gloutils


class Client:
    """Client pour le serveur mail @glo2000.ca."""

    def __init__(self, destination: str) -> None:
        """
        Prépare et connecte le socket du client `_socket`.

        Prépare un attribut `_username` pour stocker le nom d'utilisateur
        courant. Laissé vide quand l'utilisateur n'est pas connecté.
        """

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._username = None

        try:
            self._socket.connect((destination, gloutils.APP_PORT))
        except (socket.error, TimeoutError, InterruptedError):
            sys.exit(1)

    def _register(self) -> None:
        """
        Demande un nom d'utilisateur et un mot de passe et les transmet au
        serveur avec l'entête `AUTH_REGISTER`.

        Si la création du compte s'est effectuée avec succès, l'attribut
        `_username` est mis à jour, sinon l'erreur est affichée.
        """
        username = input("Entrez un nom d'utilisateur : ")
        pw = getpass.getpass("Entrez un mot de passe : ")

        payload = gloutils.AuthPayload(username=username, password=pw)
        message = gloutils.GloMessage(header=gloutils.Headers.AUTH_REGISTER, payload=payload)

        glosocket.send_mesg(self._socket, json.dumps(message))

        reply = json.loads(glosocket.recv_mesg(self._socket))

        if reply["header"] == gloutils.Headers.OK:
            self._username = username
        elif reply["header"] == gloutils.Headers.ERROR:
            print(reply["payload"]["error_message"])


    def _login(self) -> None:
        """
        Demande un nom d'utilisateur et un mot de passe et les transmet au
        serveur avec l'entête `AUTH_LOGIN`.

        Si la connexion est effectuée avec succès, l'attribut `_username`
        est mis à jour, sinon l'erreur est affichée.
        """
        username = input("Entrez un nom d'utilisateur : ")
        pw = getpass.getpass("Entrez un mot de passe : ")

        payload = gloutils.AuthPayload(username=username, password=pw)
        message = gloutils.GloMessage(header=gloutils.Headers.AUTH_LOGIN, payload=payload)
        glosocket.send_mesg(self._socket, json.dumps(message))
        reply = json.loads(glosocket.recv_mesg(self._socket))
        if reply["header"] == gloutils.Headers.OK:
            print("Connexion établie avec succès")
            self._username = username
        elif reply["header"] == gloutils.Headers.ERROR:
            print(reply["payload"]["error_message"])

    def _quit(self) -> None:
        """
        Préviens le serveur de la déconnexion avec l'entête `BYE` et ferme le
        socket du client.
        """
        message = gloutils.GloMessage(header=gloutils.Headers.BYE)
        glosocket.send_mesg(self._socket, json.dumps(message))

        self._socket.close()

    def _read_email(self) -> None:
        """
        Demande au serveur la liste de ses courriels avec l'entête
        `INBOX_READING_REQUEST`.

        Affiche la liste des courriels puis transmet le choix de l'utilisateur
        avec l'entête `INBOX_READING_CHOICE`.

        Affiche le courriel à l'aide du gabarit `EMAIL_DISPLAY`.

        S'il n'y a pas de courriel à lire, l'utilisateur est averti avant de
        retourner au menu principal.
        """

        message = gloutils.GloMessage(header=gloutils.Headers.INBOX_READING_REQUEST)
        glosocket.send_mesg(self._socket, json.dumps(message))

        reply = json.loads(glosocket.recv_mesg(self._socket))
        payload = reply["payload"]

        if len(payload["email_list"]) == 0:
            print("Il n'y a aucun courriel à consulter...")
            return
        
        for subject in payload["email_list"]:
            print(subject)
        
        choix_valide = False
        while not choix_valide:
            try:
                choice = int(input(f"Entrez votre choix [1-{len(payload['email_list'])}] : "))
            except ValueError:
                print("Choix invalide")
                continue
            if 1 <= choice <= len(payload['email_list']):
                choix_valide = True
            else:
                print("Choix invalide")

        message2 = gloutils.GloMessage(header=gloutils.Headers.INBOX_READING_CHOICE,
                                       payload=gloutils.EmailChoicePayload(choice=choice))
        glosocket.send_mesg(self._socket, json.dumps(message2))

        reply2 = json.loads(glosocket.recv_mesg(self._socket))
        payload2 = reply2["payload"]
        print(gloutils.EMAIL_DISPLAY.format(
            sender=payload2["sender"],
            to=payload2["destination"],
            subject=payload2["subject"],
            date=payload2["date"],
            body=payload2["content"]
        ))
        return

    def _send_email(self) -> None:
        """
        Demande à l'utilisateur respectivement:
        - l'adresse email du destinataire,
        - le sujet du message,
        - le corps du message.

        La saisie du corps se termine par un point seul sur une ligne.

        Transmet ces informations avec l'entête `EMAIL_SENDING`.
        """

        sender = self._username + "@" + gloutils.SERVER_DOMAIN
        destination = input("Entrez l'adresse du destinataire : ")

        subject = input("Entrez le sujet : ")
        print("Entrez le contenu du courriel, terminez la saisie avec un '.' sur sur une ligne : ")
        content = ""
        buffer = ""
        while buffer != ".\n":
            content += buffer
            buffer = input() + '\n'
        date = gloutils.get_current_utc_time()

        payload = gloutils.EmailContentPayload(
            sender=sender,
            destination=destination,
            subject=subject,
            date=date,
            content=content
        )
        message = gloutils.GloMessage(header=gloutils.Headers.EMAIL_SENDING, payload=payload)
        glosocket.send_mesg(self._socket, json.dumps(message))

        reply = json.loads(glosocket.recv_mesg(self._socket))
        if reply["header"] == gloutils.Headers.OK:
            print("Envoi effectué avec succès :)")
        elif reply["header"] == gloutils.Headers.ERROR:
            print(reply["payload"]["error_message"])
        return

    def _check_stats(self) -> None:
        """
        Demande les statistiques au serveur avec l'entête `STATS_REQUEST`.

        Affiche les statistiques à l'aide du gabarit `STATS_DISPLAY`.
        """

        message = gloutils.GloMessage(header=gloutils.Headers.STATS_REQUEST)
        glosocket.send_mesg(self._socket, json.dumps(message))

        reply = json.loads(glosocket.recv_mesg(self._socket))
        print(gloutils.STATS_DISPLAY.format(
            count=reply["payload"]["count"],
            size=reply["payload"]["size"]
        ))
        return

    def _logout(self) -> None:
        """
        Préviens le serveur avec l'entête `AUTH_LOGOUT`.

        Met à jour l'attribut `_username`.
        """
        message = gloutils.GloMessage(header=gloutils.Headers.AUTH_LOGOUT)
        glosocket.send_mesg(self._socket, json.dumps(message))

        self._username = None
        print("Déconnexion effectuée avec succès")
        return

    def run(self) -> None:
        """Point d'entrée du client."""
        should_quit = False

        while not should_quit:
            try:
                if not self._username:
                    # Authentication menu
                    print(gloutils.CLIENT_AUTH_CHOICE)
                    choix = input("Entrez votre choix [1-3] : ")

                    if choix == "1":
                        self._register()
                    elif choix == "2":
                        self._login()
                    elif choix == "3":
                        self._quit()
                        should_quit = True
                    else:
                        print("Choix invalide...")

                else:
                    # Main menu
                    print(gloutils.CLIENT_USE_CHOICE)
                    choix = input("Entrez votre choix [1-4] : ")

                    if choix == "1":
                        self._read_email()
                    elif choix == "2":
                        self._send_email()
                    elif choix == "3":
                        self._check_stats()
                    elif choix == "4":
                        self._logout()
                    else:
                        print("Choix invalide")
            except (ConnectionResetError, glosocket.GLOSocketError):
                self._quit()
                sys.exit(1)


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--destination", action="store",
                        dest="dest", required=True,
                        help="Adresse IP/URL du serveur.")
    args = parser.parse_args(sys.argv[1:])
    client = Client(args.dest)
    client.run()
    return 0


if __name__ == '__main__':
    sys.exit(_main())
