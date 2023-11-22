"""\
GLO-2000 Travail pratique 4 - Serveur
Noms et numéros étudiants:
-
-
-
"""

import hashlib
import hmac
import json
import os
import select
import socket
import sys
import re
import pathlib
import random

import glosocket
import gloutils


class Server:
    """Serveur mail @glo2000.ca."""

    def __init__(self) -> None:
        """
        Prépare le socket du serveur `_server_socket`
        et le met en mode écoute.

        Prépare les attributs suivants:
        - `_client_socs` une liste des sockets clients.
        - `_logged_users` un dictionnaire associant chaque
            socket client à un nom d'utilisateur.

        S'assure que les dossiers de données du serveur existent.
        """
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind(("127.0.0.1", gloutils.APP_PORT))
            self._server_socket.listen()
        except socket.error:
            sys.exit(1)

        self._client_socs : list[socket.socket] = []
        self._logged_users = {}

        if not os.path.exists(gloutils.SERVER_DATA_DIR):
            os.makedirs(gloutils.SERVER_DATA_DIR)
        if not os.path.exists(gloutils.SERVER_DATA_DIR + "/" + gloutils.SERVER_LOST_DIR):
            os.makedirs(gloutils.SERVER_DATA_DIR + "/" + gloutils.SERVER_LOST_DIR)
        


    def cleanup(self) -> None:
        """Ferme toutes les connexions résiduelles."""
        for client_soc in self._client_socs:
            client_soc.close()
        self._server_socket.close()

    def _accept_client(self) -> None:
        """Accepte un nouveau client."""

        client_socket, _ = self._server_socket.accept()
        self._client_socs.append(client_socket)

    def _remove_client(self, client_soc: socket.socket) -> None:
        """Retire le client des structures de données et ferme sa connexion."""
        try:
            self._logged_users.pop(client_soc)
            self._client_socs.remove(client_soc)
        except (KeyError, ValueError):
            # No need to do anything, the client soc isn't in containers
            pass

        client_soc.close()

    def _create_account(self, client_soc: socket.socket,
                        payload: gloutils.AuthPayload
                        ) -> gloutils.GloMessage:
        """
        Crée un compte à partir des données du payload.

        Si les identifiants sont valides, créee le dossier de l'utilisateur,
        associe le socket au nouvel l'utilisateur et retourne un succès,
        sinon retourne un message d'erreur.
        """
        userName = payload["username"].upper()
        pw = payload["password"]

        # Make sure username only contains alphanumerical characters
        pattern = re.compile(r"[a-zA-Z0-9_\.-]+")
        validUsername = pattern.fullmatch(userName)
        
        # Make sure there is not already an account with this name in the server data dir
        newUsername = not os.path.exists(gloutils.SERVER_DATA_DIR + "/" + userName)

        # Make sure the password is secure enough
        validPwLength = len(pw) >= 10

        pwContainsNumber = False
        pwContainsMin = False
        pwContainsMaj = False
        for letter in pw:
            if letter.isnumeric():
                pwContainsNumber = True
            if letter.islower():
                pwContainsMin = True
            if letter.isupper():
                pwContainsMaj = True
        
        validCredentials = validUsername and newUsername and validPwLength and pwContainsNumber and pwContainsMin and pwContainsMaj

        if validCredentials:
            os.makedirs(gloutils.SERVER_DATA_DIR + "/" + userName)

            # hash password and add to folder
            encodedPw = pw.encode('utf-8')
            hasher = hashlib.sha3_224()
            hasher.update(encodedPw)
            data = {"password_hash": hasher.hexdigest()}
            with open(gloutils.SERVER_DATA_DIR + "/" + userName + "/" + gloutils.PASSWORD_FILENAME, 'w') as f:
                json.dump(data, f)
            
            # confirm success to client
            message = gloutils.GloMessage(header=gloutils.Headers.OK)

            self._logged_users[client_soc] = userName
        else:
            error_string = ""
            if not validUsername:
                error_string += "Le nom d'utilisateur n'est pas alphanumérique\n"
            if not newUsername:
                error_string += "Ce nom d'utilisateur est déjà pris\n"
            if not validPwLength:
                error_string += "Le mot de passe doit contenir au moins 10 caractères\n"
            if not pwContainsNumber:
                error_string += "Le mot de passe doit contenir au moins un chiffre\n"
            if not pwContainsMin:
                error_string += "Le mot de passe doit contenir au moins une minuscule\n"
            if not pwContainsMaj:
                error_string += "Le mot de passe doit contenir au moins une majuscule\n"
            
            message = gloutils.GloMessage(header=gloutils.Headers.ERROR,
                                          payload=gloutils.ErrorPayload(error_message=error_string))

        return message

    def _login(self, client_soc: socket.socket, payload: gloutils.AuthPayload
               ) -> gloutils.GloMessage:
        """
        Vérifie que les données fournies correspondent à un compte existant.

        Si les identifiants sont valides, associe le socket à l'utilisateur et
        retourne un succès, sinon retourne un message d'erreur.
        """
        userName = payload["username"].upper()
        pw = payload["password"]
        validUsername = validPw = False

        validUsername = os.path.exists(gloutils.SERVER_DATA_DIR + "/" + userName)

        # Verify password (only if username exists)
        if validUsername:
            with open(gloutils.SERVER_DATA_DIR + "/" + userName + "/" + gloutils.PASSWORD_FILENAME, 'r') as f:
                storedHash = json.load(f)
            given_hash = hashlib.sha3_224()
            given_hash.update(pw.encode('utf-8'))
            validPw = hmac.compare_digest(given_hash.hexdigest(), storedHash["password_hash"])
        print("valid username\t" + str(validUsername) + "\nvalid password\t" + str(validPw))
        if validUsername and validPw:
            message = gloutils.GloMessage(header=gloutils.Headers.OK)
            self._logged_users[client_soc] = userName
        else:
            error_string = ""
            if not validUsername:
                error_string = "Le nom d'utilisateur n'est pas valide"
            elif not validPw:
                error_string = "Le mot de passe n'est pas valide"

            message = gloutils.GloMessage(header=gloutils.Headers.ERROR,
                                          payload=gloutils.ErrorPayload(error_message=error_string))

        return message

    def _logout(self, client_soc: socket.socket) -> None:
        """Déconnecte un utilisateur."""

        self._logged_users.pop(client_soc)

    def _get_email_list(self, client_soc: socket.socket
                        ) -> gloutils.GloMessage:
        """
        Récupère la liste des courriels de l'utilisateur associé au socket.
        Les éléments de la liste sont construits à l'aide du gabarit
        SUBJECT_DISPLAY et sont ordonnés du plus récent au plus ancien.

        Une absence de courriel n'est pas une erreur, mais une liste vide.
        """

        folder = gloutils.SERVER_DATA_DIR + "/" + self._logged_users[client_soc]
        json_files = [f for f in os.listdir(folder) if f != gloutils.PASSWORD_FILENAME]

        file_list = []
        for file in json_files:
            with open(folder + "/" + file, 'r') as f:
                file_list.append(json.load(f))
        
        # List items format : (envoyeur, sujet, date)
        email_list = [(mail["sender"], mail["subject"], mail["date"]) for mail in file_list]

        # Sort list
        sorted_list = sorted(email_list, key=lambda x : x[2], reverse=True)

        subject_list = []
        for i, email in enumerate(sorted_list):
            display = gloutils.SUBJECT_DISPLAY.format(
                number = i+1,
                sender = email[0],
                subject = email[1],
                date = email[2]
            )
            subject_list.append(display)

        return gloutils.GloMessage(header=gloutils.Headers.OK,
                                   payload=gloutils.EmailListPayload(email_list=subject_list))

    def _get_email(self, client_soc: socket.socket,
                   payload: gloutils.EmailChoicePayload
                   ) -> gloutils.GloMessage:
        """
        Récupère le contenu de l'email dans le dossier de l'utilisateur associé
        au socket.
        """
        folder = gloutils.SERVER_DATA_DIR + "/" + self._logged_users[client_soc]
        json_files = [f for f in os.listdir(folder) if f != gloutils.PASSWORD_FILENAME]

        file_list = []
        for file in json_files:
            with open(folder + "/" + file, 'r') as f:
                file_list.append(json.load(f))

        # Sort list
        sorted_list = sorted(file_list, key=lambda x : x["date"], reverse=True)

        chosen_email = sorted_list[payload["choice"] -1]
        sender = chosen_email["sender"]
        subject = chosen_email["subject"]
        destination = chosen_email["destination"]
        date = chosen_email["date"]
        content = chosen_email["content"]

        return gloutils.GloMessage(header=gloutils.Headers.OK,
                                   payload=gloutils.EmailContentPayload(
                                       sender=sender,
                                       subject=subject,
                                       destination=destination,
                                       date=date,
                                       content=content
                                   ))

    def _get_stats(self, client_soc: socket.socket) -> gloutils.GloMessage:
        """
        Récupère le nombre de courriels et la taille du dossier et des fichiers
        de l'utilisateur associé au socket.
        """

        folder = pathlib.Path(gloutils.SERVER_DATA_DIR + "/" + self._logged_users[client_soc])
        json_files = [f for f in os.listdir(folder) if f != gloutils.PASSWORD_FILENAME]

        nb_of_emails = len(json_files)
        
        total_size = 0
        for file in folder.iterdir():
            total_size += os.path.getsize(file)

        return gloutils.GloMessage(header=gloutils.Headers.OK,
                                   payload=gloutils.StatsPayload(
                                       count=nb_of_emails,
                                       size=total_size
                                   ))

    def _send_email(self, payload: gloutils.EmailContentPayload
                    ) -> gloutils.GloMessage:
        """
        Détermine si l'envoi est interne ou externe et:
        - Si l'envoi est interne, écris le message tel quel dans le dossier
        du destinataire.
        - Si le destinataire n'existe pas, place le message dans le dossier
        SERVER_LOST_DIR et considère l'envoi comme un échec.
        - Si le destinataire est externe, considère l'envoi comme un échec.

        Retourne un messange indiquant le succès ou l'échec de l'opération.
        """
        intern = exists = False
        file_name = "mail" + str(random.randrange(1000000))
        destination = payload["destination"][:-11]

        if payload["destination"][-10:] == gloutils.SERVER_DOMAIN.lower():
            intern = True

        if os.path.exists(gloutils.SERVER_DATA_DIR + "/" + destination):
            exists = True
        
        if intern and exists:
            with open(gloutils.SERVER_DATA_DIR + "/" + destination + "/" + file_name, 'w') as f:
                json.dump(payload, f)

            message = gloutils.GloMessage(header=gloutils.Headers.OK)
        
        else:
            error_string = ""
            if intern == False:
                with open(gloutils.SERVER_DATA_DIR + "/" + gloutils.SERVER_LOST_DIR + file_name, 'w') as f:
                    json.dump(payload, f)

                error_string = "Le destinataire est externe au serveur"
            elif exists == False:
                error_string = "Cet utilisateur n'existe pas"
            
            message = gloutils.GloMessage(header=gloutils.Headers.ERROR,
                                          payload=gloutils.ErrorPayload(error_message=error_string))

        return message

    def run(self):
        """Point d'entrée du serveur."""
        while True:
            # Select readable sockets
            readable_sockets : list[socket.socket] = [sock for sock in self._client_socs if not sock._closed]
            readable_sockets.append(self._server_socket)
            waiters = select.select(readable_sockets, [], [])[0]
            for waiter in waiters:
                # Handle sockets
                if waiter == self._server_socket:
                    self._accept_client()
                    print("client accepted")
                else:
                    try:
                        print("reading data")
                        data = glosocket.recv_mesg(waiter)
                        data = json.loads(data)
                        header = data["header"]
                        payload = data.get("payload")

                        if header == gloutils.Headers.AUTH_REGISTER:
                            print("reveived")
                            reply = self._create_account(waiter, payload)
                            print(str(reply))

                        elif header == gloutils.Headers.AUTH_LOGIN:
                            print("==login==")
                            reply = self._login(waiter, payload)
                            print(str(reply))
                        
                        elif header == gloutils.Headers.BYE:
                            reply = self._remove_client(waiter)
                            continue

                        elif header == gloutils.Headers.INBOX_READING_REQUEST:
                            reply = self._get_email_list(waiter)
                        
                        elif header == gloutils.Headers.INBOX_READING_CHOICE:
                            reply = self._get_email(waiter, payload)
                        
                        elif header == gloutils.Headers.EMAIL_SENDING:
                            reply = self._send_email(payload)
                        
                        elif header == gloutils.Headers.STATS_REQUEST:
                            reply = self._get_stats(waiter)
                        
                        elif header == gloutils.Headers.AUTH_LOGOUT:
                            reply = self._logout(waiter)
                            continue
                        
                        glosocket.send_mesg(waiter, json.dumps(reply))
                        print("reply sent")

                    except (ConnectionResetError, glosocket.GLOSocketError):
                        self._remove_client(waiter)


def _main() -> int:
    server = Server()
    try:
        server.run()
    except KeyboardInterrupt:
        server.cleanup()
        sys.exit(1)
    return 0


if __name__ == '__main__':
    sys.exit(_main())
