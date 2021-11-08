#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, telegram
import asyncio
import json
import os, subprocess
import http.client
from io import StringIO
import requests
import os.path
from bs4 import BeautifulSoup
from urllib.request import urlopen
from urllib.parse import urlparse
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Token
token = ""

class Link:
    """Link object that contains URL and site."""
    def __init__(self, url=None, site=None):
        self.url = url
        self.site = site


class Component:
    def __init__(self, id=None, name=None, comp_type=None, chosen_price=None, links=None):
        self.id = id
        self.name = name
        self.comp_type = comp_type
        self.chosen_price = chosen_price # user input price through /filter_price cmd
        self.links = links

    def to_string(self):
        sb = ""
        sb += self.id + " "
        sb += self.name
        sb += " - " + self.comp_type
        sb += " - ["
        for l in self.links:
            sb += l.url + " - " + l.site + ", "
        sb += "]"
        return sb


class ConfManager:
    """Reads component configuration file."""
    def __init__(self, userID):
        self.userID = userID 

    def read_components(self, filter_mode=None, filter=None):
        components = []
        if not os.path.exists(self.userID + '-components.json'):
            print("Creating new file for " + self.userID)
            f = open(self.userID + "-components.json", 'w')
            f.write("[]")
            f.close()

        input_file = open(self.userID + '-components.json')
        comps = json.load(input_file)
        for c in comps:
            if (filter_mode == 'cpu' and c['comp_type'] == 'cpu') \
                or (filter_mode == 'gpu' and c['comp_type'] == 'gpu') \
                    or (filter_mode == 'entry' and c['id'] in [d.strip() for d in filter.split(',')]) \
                        or (filter_mode is None or filter_mode == 'all'): 
                component = Component()
                component.id = c['id']
                component.name = c['name']
                component.comp_type = c['comp_type']
                component.chosen_price = c['chosen_price']
                links = c['links']
                component.links = []
                for l in links:
                    link = Link()
                    link.url = l['url']
                    link.site = l['site']
                    component.links.append(link)
                components.append(component)
        return components

    def get_max_id(self, filename):
        json_array = json.load(open(filename))
        max_id = len(json_array)
        return max_id


    def read_json(self):
        if not os.path.exists(self.userID + '-components.json'):
            print("Creating new file for " + self.userID)
            f = open(self.userID + "-components.json", 'w')
            f.write("[]")
            f.close()

        input_file = open(self.userID + '-components.json')
        comps = json.load(input_file)
        return comps

    def remove(self, id, filename):
        json_array = json.load(open(filename))
        for i in range(len(json_array)):
            if int(json_array[i]['id']) == id:
                json_array.pop(i)
                break
        if os.path.exists(filename):
            with open(filename, "r+") as f:
                f.seek(0)
                json.dump(json_array, f)
                f.truncate()
                f.close()
            return 0
        return -1

    def set_chosen_price(self, id, filename, chosen_price):
        json_array = json.load(open(filename))
        for i in range(len(json_array)):
            if int(json_array[i]['id']) == id:
                json_array[i]['chosen_price'] = str(chosen_price)
                break
        if not os.path.exists(filename):
            open(filename, 'w').close()
        with open(filename, "r+") as f:
            f.seek(0)
            json.dump(json_array, f)
            f.truncate()
            f.close()

    def print_entries(self, components):
        result_string = ""
        for c in components:
            result_string += "ID: " + c.id + '\n'
            result_string += "Nome: " + c.name + '\n'
            result_string += "Tipo: " + c.comp_type + '\n'
            if float(c.chosen_price) == 0:
                result_string += f"Prezzo da filtrare: nessuno\n"
            else:
                result_string += f"Prezzo da filtrare: {c.chosen_price}\n"
            for l in c.links:
                result_string += "Link: " + l.url + " -- " + l.site + '\n'
            result_string += '\n\n'
        return result_string



class ParserUnieuro:
    def parse(self, link=None, chosen_price=0):
        result_string = ""
        curl_cmd = "curl '" + link + "'"

        page = subprocess.getoutput([curl_cmd])

        soup = BeautifulSoup(page, features="html.parser")
        product_name  = " ".join(soup.find("h1", {"class": "subtitle"}).text.split()) 
        not_available  = " ".join(soup.find("a", {"class": "btn btn-blue-normal md-trigger single-btn"}).text.split()) == "Notifica disponibilità"
        product_price_int  = " ".join(soup.find("div", {"class": "prices-content"}).find("span", {"class": "integer"}).text.split()) 
        product_price_cents  = " ".join(soup.find("div", {"class": "prices-content"}).find("span", {"class": "decimal"}).text.split())
        product_price = product_price_int + product_price_cents
        product_link = link
        product_price = product_price.replace(',', '.')
        if not_available is False: # available, notify user
            if float(chosen_price) == 0 or (float(chosen_price) > 0 and float(product_price) <= float(chosen_price)):
                result_string += product_name + ": " + product_price + "€" + " (DISPONIBILE: " + product_link + ")\n\n"
        
        return result_string 

    def get_prod_name(self, link=None):
        curl_cmd = "wget -O - " + link
        
        page = subprocess.getoutput([curl_cmd])

        soup = BeautifulSoup(page, features="html.parser")
        product_name  = " ".join(soup.find("h1", {"class": "subtitle"}).text.split()) 
        return product_name

class ParserAMD:
    def parse(self, link=None, chosen_price=0):
        result_string = ""

        curl_cmd = "curl '" + link + "'" + " -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8' -H 'Accept-Language: it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3' --compressed -H 'Referer: https://www.amd.com/en' -H 'Connection: keep-alive' -H 'Upgrade-Insecure-Requests: 1'"


        page = subprocess.getoutput([curl_cmd])
        soup = BeautifulSoup(page, features="html.parser")
        product_name  = " ".join(soup.find("div", {"class": "product-page-description col-flex-lg-5 col-flex-sm-12"}).find("h2").text.split()) 
        product_price  = " ".join(soup.find("div", {"class": "product-page-description col-flex-lg-5 col-flex-sm-12"}).find("h4").text.split())
        product_price = product_price[:-1].strip() # cut the Euro symbol and the space at the end
        product_price = product_price.replace(',', '.')
        available = True
        #available  = " ".join(
        for divfound in soup.findAll("div", {"class": "product-page-description col-flex-lg-5 col-flex-sm-12"}):
            child = divfound.find("p", {"class": "product-out-of-stock"}) 
            if child != None:
                available = False

        product_link = link

        if available: # available, notify user
            if float(chosen_price) == 0 or (float(chosen_price) > 0 and float(product_price) <= float(chosen_price)):
                result_string += product_name + ": " + product_price + "€" + " (DISPONIBILE: " + product_link + ")\n\n"
        
        return result_string 

    def get_prod_name(self, link=None):
        curl_cmd = "curl '" + link + "'" + " -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:84.0) Gecko/20100101 Firefox/84.0' -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8' -H 'Accept-Language: it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3' --compressed -H 'Referer: https://www.amd.com/en' -H 'Connection: keep-alive' -H 'Upgrade-Insecure-Requests: 1'"
        print(curl_cmd)
        
        page = subprocess.getoutput([curl_cmd])

        soup = BeautifulSoup(page, features="html.parser")
        product_name  = " ".join(soup.find("div", {"class": "product-page-description col-flex-lg-5 col-flex-sm-12"}).find("h2").text.split()) 
        return product_name


class ParserAmazon:
    def parse(self, link=None, chosen_price=0):
        result_string = ""
        curl_cmd = "wget -O - " + link
        product_link = link

        page = subprocess.getoutput([curl_cmd])
    #    print(page) # debug

        soup = BeautifulSoup(page, features="html.parser")
        product_name  = " ".join(soup.find("span", {"id": "productTitle"}).text.split()) 

        # get availability
        available = False
        product_price = soup.find("span", {"id": "priceblock_ourprice"})
        if product_price:
            product_price = " ".join(product_price.text.split())[:-len(product_price)]
            available = True
    #    else: # could be available but you have to get vendor's price (doesn't work atm)
    #        vendors_list = soup.find_all("div", {"id": "aod-offer-list"}) 
    #        if vendors_list:
    #            available = True
    #            for child in vendors_list:
    #                product_price += child.find("span", {"class": "a-price-whole"}.text.split()).join(", ")
    #                print(product_price)


        if available: # available, put price
            chosen_price = float(chosen_price)
            product_price = product_price.replace(',', '.')
            if float(chosen_price) == 0 or (float(chosen_price) > 0 and float(product_price) <= float(chosen_price)):
    #        product_price  = " ".join(soup.find("span", {"id": "priceblock_ourprice"}).text.split())
    #        if float(product_price) < chosen_price: # future develop
                result_string += product_name + ": " + product_price + "€" + " (DISPONIBILE): " + product_link + "\n\n"

        return result_string

    def get_prod_name(self, link=None):
#        print(link)
        curl_cmd = "wget -O - " + link
        
        page = subprocess.getoutput([curl_cmd])

        soup = BeautifulSoup(page, features="html.parser")
        product_name  = " ".join(soup.find("span", {"id": "productTitle"}).text.split()) 
        return product_name


class ParsersFactory:
    @staticmethod
    def get_parser(hostname):
        if hostname == 'www.unieuro.it':
            return ParserUnieuro()
        elif hostname == 'www.amazon.it':
            return ParserAmazon()
        elif hostname == 'www.amd.com':
            return ParserAMD()


#    result_string += get_amazon_product_info("https://www.amazon.it/dp/B07ZZVWB4L/ref=gw_it_desk_mso_smp_shl_q4?pf_rd_r=J7BMS8M9EYV0ARSCAG2F&pf_rd_p=6fa61aaa-d284-4e1b-9037-13deb7117e7d&pd_rd_r=69bdc18e-0804-4a43-8e44-be56571ccc48&pd_rd_w=APPHn&pd_rd_wg=yJxB1&ref_=pd_gw_unk") # debug
#    result_string += get_amazon_product_info("https://www.amazon.it/ZOTAC-GAMING-GeForce-3070-Twin/dp/B08LBVNKT1")
#    result_string += get_amazon_product_info("https://www.amazon.it/PNY-Scheda-Grafica-GeForce-Gaming/dp/B08HBJB7YD/")
#    result_string += get_amazon_product_info("https://www.amazon.it/ZOTAC-Scheda-grafica-GEFORCE-ZT-A30700E-10P/dp/B08HRBR7K9/")

#copiare sul json da qui
#    result_string += get_amazon_product_info("https://www.amazon.it/Gigabyte-GeForce-RTX-3070-VISION/dp/B08LNWPYRS")
#    result_string += get_amazon_product_info("https://www.amazon.it/Gigabyte-GeForce-RTX-3070-EAGLE/dp/B08MDCF8Z8")
#    result_string += get_amazon_product_info("https://www.amazon.it/MSI-GeForce-DisplayPort-supporto-Afterburner/dp/B08LNQTSCT")
#    result_string += get_amazon_product_info("https://www.amazon.it/PNY-Scheda-Grafica-GeForce-UPRISING/dp/B08HBF5L3K")
#    result_string += get_amazon_product_info("https://www.amazon.it/Gigabyte-GeForce-RTX-3070-GAMING/dp/B08KHL21CV")
#    result_string += get_amazon_product_info("https://www.amazon.it/Gigabyte-GeForce-GAMING-Scheda-Grafica/dp/B08P3JL63Y/")
#    result_string += get_amazon_product_info("https://www.amazon.it/Gigabyte-GeForce-EAGLE-Scheda-Grafica/dp/B08P3JPX8P")
#    result_string += get_amazon_product_info("https://www.amazon.com/dp/B08R876RTH/?tag=NoRef")
#    result_string += get_amazon_product_info("https://www.amazon.it/Zotac-Gaming-GeForce-3060-ZT-A30610E-10M/dp/B08P34VCVN/")



def callback_update(context: telegram.ext.CallbackContext):
    """Updater on selected CPUs and GPUs."""
    user_data = context.job.context['user_data']['user_data']

    result_string = ""
    reader = ConfManager(user_data['username'])
    cmp_list = reader.read_components(user_data['search_mode'], user_data.get('ids'))
    for cmp in cmp_list:
        for link in cmp.links:
            parser = None
            if link.site == 'www.amazon.it':
                parser = ParserAmazon()
                result_string += parser.parse(link.url, cmp.chosen_price) 
            elif link.site == 'www.unieuro.it':
                parser = ParserUnieuro()
                result_string += parser.parse(link.url, cmp.chosen_price) 
            elif link.site == 'www.amd.com':
                parser = ParserAMD()
                result_string += parser.parse(link.url, cmp.chosen_price) 
        
    if result_string:
        context.bot.send_message(chat_id=context.job.context['chat_id'], text=result_string)


# Define a few command handlers. These usually take the two arguments update and
# context. Error handlers also receive the raised TelegramError object in error.


def search(update: telegram.Update, context: telegram.ext.CallbackContext):
    """Send a message when the command /search is issued."""

    search_modes = ["all", "cpu", "gpu", "entry"]

    # Initializing default interval if user didn't set it
    if 'interval' not in context.bot_data:
        context.bot_data['interval'] = 5 # default: 5 minute
    interval = context.bot_data['interval']

    user_data = dict()
    if context.args[0] in search_modes:
        user_data['search_mode'] = context.args[0]
        user_data['username'] = update.message.chat.username
        if context.args[0] == 'entry': # need to set also the entry if the search cmd has 'entry' option
            user_data['ids'] = context.args[1] # i.e /search 0,1 will get you updates only on components with id = 0 and 1

        print("USER DATA: ")
        print(user_data)

        # start job 
        update.message.reply_text(f'Ricerca automatica attivata. Intervallo impostato: {interval} minuti. Per stoppare la ricerca: /stop')
        j = context.job_queue
        context.user_data['user_data'] = user_data 
        next_job = j.run_repeating(callback_update, 60 * interval, 0, context={'chat_id': update.message.chat_id, 'user_data': context.user_data, 'chat_data': context.chat_data})
        context.bot_data['next_job'] = next_job
    else:
        update.message.reply_text("Inserisci un'opzione valida (all, gpu, cpu, <entry>)")
        raise ValueError("Opzione " + context.args[0] + " non valida")

   

def stop(update, context):
    """Stops the checker."""
    update.message.reply_text('Ricerca automatica stoppata. Per riattivarla: /search')
    context.bot_data['next_job'].enabled = False


def set_timer(update, context):
    """Configure the time interval in seconds."""
    try:
        context.bot_data['interval'] = int(context.args[0])
        interval = context.bot_data['interval']
        update.message.reply_text(f'Timer correttamente aggiornato a {interval} minuti') 
    except (IndexError, ValueError):
        update.message.reply_text('Inserisci un numero valido.')



def show_entries(update, context):
    reader = ConfManager(update.message.chat.username)
    cmp_list = reader.read_components()
    entries_string = reader.print_entries(cmp_list)
    if entries_string:
        update.message.reply_text(entries_string)
    else:
        update.message.reply_text("Non hai ancora aggiunto nessun componente.")


def add_entry(update, context):
    comp_types = ['cpu', 'gpu']
    comp_type = context.args[0]
    link = context.args[1]
    if comp_type in comp_types and len(context.args) == 2:
        reader = ConfManager(update.message.chat.username)
        max_id = reader.get_max_id(update.message.chat.username + "-components.json")
        max_id = str(max_id)
        json_array = reader.read_json()
        parser = ParsersFactory.get_parser(urlparse(link.strip()).hostname)
        prod_name = parser.get_prod_name(link.strip())
        data = {
            "id": max_id,
            "name": prod_name,
            "comp_type": comp_type.strip(),
            "chosen_price": "0",
            "links": [
                {
                    "url": link.strip(),
                    "site": urlparse(link.strip()).hostname
                }
            ]
        }
        json_array.append(data)
        if not os.path.exists(update.message.chat.username + "-components.json"):
            f = open(update.message.chat.username + "-components.json", 'w')
            f.write("[]")
            f.close()
        with open(update.message.chat.username + "-components.json", "r+") as f:
            f.seek(0)
            json.dump(json_array, f)
            f.truncate()
            f.close()
        update.message.reply_text(f"Componente inserito con successo (ID: {max_id})! /show_entries per vederlo.")
    else:
        update.message.reply_text("Componente inserito non valido. Dai un'occhiata ad /help per i comandi.") 


def rem_entry(update, context):
    entry = context.args[0]
    if len(entry) == 1 and entry[0].isnumeric():
        id = int(entry[0])
        reader = ConfManager(update.message.chat.username)
        if reader.remove(id, update.message.chat.username + "-components.json") < 0:
            update.message.reply_text("Sintassi non valida. Dai un'occhiata ad /help per i comandi.") 
        else:
            update.message.reply_text("Componente rimosso con successo!")


def filter_price(update, context):
    try:
        id = int(context.args[0])
        chosen_price = int(context.args[1]) 
        reader = ConfManager(update.message.chat.username)
        reader.set_chosen_price(id, update.message.chat.username + "-components.json", chosen_price)
        update.message.reply_text(f"Aggiornato sulla entry {id} il prezzo limite di {chosen_price} €.")
    except (IndexError, ValueError):
        update.message.reply_text('Sintassi non valida. Digita /help per mostrare i comandi.')


def help(update, context):
    """Send a message when the command /help is issued."""
    sb = ""
    sb += "Comandi:\n"
    sb += "/search all          cerca tutti i componenti da te inseriti\n"
    sb += "/search cpu          cerca solo i processori\n"
    sb += "/search gpu          cerca solo le schede video\n"
    sb += "/search entry 1,2    cerca solo i componenti con id 1 e 2\n"
    sb += "/stop                ferma la ricerca\n"
    sb += "/set_timer 5         configura come intervallo di tempo tra una ricerca e un-altra 5 minuti\n"
    sb += "/show_entries        mostra le entry da te inserite\n"
    sb += "/add [cpu|gpu] <link>        aggiunge una entry\n"
    sb += "/rem <id>            rimuove una entry\n"
    sb += "/filter_price <id>  <price>    filtra le ricerche su un componente in base al prezzo\n"
    update.message.reply_text(sb)

def start(update, context):
    update.message.reply_text("Digita /help per i comandi. Buona fortuna con gli acquisti!")

def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def enable_http_logging():
    try:
        import http.client as http_client
    except ImportError:
        # Python 2
        import httplib as http_client
    http_client.HTTPConnection.debuglevel = 1

    # You must initialize logging, otherwise you'll not see debug output.
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


def main():
    """Start the bot."""

    #enable_http_logging()

    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    updater = Updater(token, use_context=True)


    # Get the dispatcher to register handlers
    dp = updater.dispatcher
    

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("search", search))
    dp.add_handler(CommandHandler("help", help))
    dp.add_handler(CommandHandler("stop", stop))
    dp.add_handler(CommandHandler("set_timer", set_timer))
    dp.add_handler(CommandHandler("show_entries", show_entries))
    dp.add_handler(CommandHandler("add", add_entry))
    dp.add_handler(CommandHandler("rem", rem_entry))
    dp.add_handler(CommandHandler("filter_price", filter_price))


    # log all errors
    dp.add_error_handler(error)


    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()




if __name__ == '__main__':
    main()
