import sys
import os
from os import environ
from flask_cors import CORS
from flask import Flask, request, jsonify
from invokes import invoke_http

import amqp_setup
import pika
import json
import copy

app = Flask(__name__)
CORS(app)

inventory_URL = environ.get('inventory_URL') or "http://localhost:5001/inventory"
transaction_URL = environ.get('transaction_URL') or "http://localhost:5005/transaction"


@app.route("/washing_vendor_update", methods=['POST'])
def washing_vendor_update():
    # Simple check of input format and data of the request are JSON
    if request.is_json:
        try:
            transaction = request.get_json()
            print("\nReceived a transaction in JSON:", transaction)

            # do the actual work
            # 1. Send transaction info
            result = processTransaction(transaction)
            return jsonify(result), result["code"]

        except Exception as e:
            # Unexpected error in code
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            ex_str = str(e) + " at " + str(exc_type) + ": " + \
                fname + ": line " + str(exc_tb.tb_lineno)
            print(ex_str)

            return jsonify({
                "code": 500,
                "message": "washing_vendor_update.py internal error: " + ex_str
            }), 500

    # if reached here, not a JSON request.
    return jsonify({
        "code": 400,
        "message": "Invalid JSON input: " + str(request.get_data())
    }), 400


def processTransaction(transaction):
    # 2. Update inventory
    # Invoke the inventory microservice
    print('\n-----Invoking inventory microservice-----')
    qty = transaction["quantity"]
    data = {"quantity": qty}
    inventory_result = invoke_http(
        inventory_URL + "/return/" + transaction["packaging_type"], method='PUT', json=data)
    print('inventory_result:', inventory_result)

    # Check the update inventory result; if a failure, print error message
    code = inventory_result["code"]
    if code not in range(200, 300):

        print("Update inventory failed")

        # 3. Return error
        return {
            "code": 404,
            "data": {"inventory_result": inventory_result},
            "message": "Inventory not found."
        }

    # 4. Send transaction info
    print('\n\n-----Publishing the (Transaction info) message with routing_key=transaction-----')
    message = json.dumps(transaction)
    amqp_setup.channel.basic_publish(exchange=amqp_setup.exchangename, routing_key="transaction",
                                     body=message)

    print("\nUpdate Transaction published to RabbitMQ Exchange.\n")

    # 4. Send notification
    print('\n\n-----Publishing the (Transaction info) message with routing_key=notification-----')
    message = copy.deepcopy(transaction)
    message["notification_type"] = "update"
    message = json.dumps(message)

    amqp_setup.channel.basic_publish(exchange=amqp_setup.exchangename, routing_key="notification",
                                     body=message)

    print("\nUpdate Transaction published to RabbitMQ Exchange.\n")

    # 6. Return created transaction
    return {
        "code": 201,
        "data": {
            "inventory_result": inventory_result
        }
    }


# Execute this program if it is run as a main script (not by 'import')
if __name__ == "__main__":
    print("This is flask " + os.path.basename(__file__) +
          " for creating washing vendor transaction...")
    app.run(host="0.0.0.0", port=5102, debug=True)
    # Notes for the parameters:
    # - debug=True will reload the program automatically if a change is detected;
    #   -- it in fact starts two instances of the same flask program,
    #       and uses one of the instances to monitor the program changes;
    # - host="0.0.0.0" allows the flask program to accept requests sent from any IP/host (in addition to localhost),
    #   -- i.e., it gives permissions to hosts with any IP to access the flask program,
    #   -- as long as the hosts can already reach the machine running the flask program along the network;
    #   -- it doesn't mean to use http://0.0.0.0 to access the flask program.
