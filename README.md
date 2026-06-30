# **Software Requirements Specification (SRS) Document**

## **Brief Problem Statement**

The client requires a system that supports both home delivery and takeaway. The system should allow customers to place, track, and manage orders, restaurant managers should be able to oversee each order and the system must assign delivery agents to each order.

---

## **System Requirements**

* The system should support both home delivery and takeaway.  
* The system should maintain data across multiple instances.  
* The customers should be able to track their order and find out how long it will take to deliver.  
* Delivery agents must be assigned automatically when an order is placed.  
* The system must handle multiple concurrent orders.  
* The manager should be able to view all orders for a restaurant.

---

## **Users Profile**

* **Customers**: Users who place orders, track delivery, and manage their account.  
* **Delivery Agents**: System-assigned personnel responsible for delivering orders.  
* **Restaurant Managers**: Users who manage order processing and delivery assignments.  
* **System Administrator**: Oversees system maintenance and database management.

---

## **Feature Requirements**

| No. | Use Case Name | Description |
| ----- | ----- | ----- |
| 1 | Place Order | Customer selects a restaurant, dish, and order type (delivery/takeaway) to place an order. |
| 2 | Track Order | Customer checks order status and remaining delivery time. |
| 3 | Assign Delivery Agent | System automatically assigns an available delivery agent to a delivery order. |
| 4 | Manager Login | Restaurant managers log in using their credentials to access management functions. |
| 5 | Manage Orders | Restaurant managers view all orders for their restaurant. |
| 6 | Check Pending Deliveries | Restaurant managers view pending deliveries for their restaurant. |

---

## **Use Case Diagram**

![alt text](image.png)
---

## **Use Case Descriptions**

### **Use Case Number: UC-01**

**Use Case Name:** Place Order  
**Overview:** Customers can browse available restaurants, select a dish (numbered 1–20), choose the order type (Delivery or Takeaway), and confirm their order.  
**Actors:** Customer, System  
**Precondition:** The customer is using the CLI interface.  
**Flow:**

1. Customer selects the "Place Order" option.  
2. Customer chooses a restaurant from a displayed list.  
3. Customer selects a dish by entering a number between 1 and 20\.  
4. Customer selects the order type:  
   * If "Delivery" is chosen, the system automatically assigns a delivery agent.  
   * If "Takeaway" is chosen, no delivery agent is assigned.  
5. The system sets a random estimated delivery time (between 5 and 20 minutes from the current time).  
6. The system records the order details in the MySQL database.

**Postcondition:** Order is placed successfully and recorded with a status of "Pending".

---

### **Use Case Number: UC-02**

**Use Case Name:** Track Order  
**Overview:** Customers can check the status of their orders and view the remaining time until delivery.  
**Actors:** Customer, System  
**Precondition:** The customer has at least one active order.  
**Flow:**

1. Customer selects the "Track Order" option.  
2. The system retrieves the customer’s orders from the database.  
3. The system calculates and displays the remaining time for each order (or "delivered" if time has expired). 

**Postcondition:** The customer is informed of the current status of their orders.

---

### **Use Case Number: UC-03**

**Use Case Name:** Assign Delivery Agent  
**Overview:** For delivery orders, the system automatically assigns an available delivery agent from a predefined list.  
**Actors:** System, Delivery Agent  
**Precondition:** A customer places an order with "Delivery" selected.  
**Flow:**

1. The customer chooses "Delivery" as the order type.  
2. The system randomly selects an available delivery agent.  
3. The selected delivery agent is recorded with the order. 

**Postcondition:** The delivery order is linked with an assigned delivery agent.

---

### **Use Case Number: UC-04**

**Use Case Name:** Manager Login  
**Overview:** Restaurant managers log in to access the system's management functionalities.  
**Actors:** Restaurant Manager, System  
**Precondition:** Manager credentials exist in the system’s MySQL database.  
**Flow:**

1. Manager selects the "Manager" option from the main menu.  
2. The system displays a list of restaurants.  
3. Manager selects their restaurant.  
4. Manager enters their name and password.  
5. The system verifies the credentials.  
6. Upon successful verification, the manager gains access to management options. 

**Postcondition:** The manager is logged in and can view/manage orders.

---

### **Use Case Number: UC-05**

**Use Case Name:** Manage Orders  
**Overview:** Logged-in restaurant managers can view all orders for their restaurant.  
**Actors:** Restaurant Manager, System  
**Precondition:** Manager is logged in.  
**Flow:**

1. Manager selects "Manage Orders" from the management menu.  
2. The system retrieves all orders associated with the restaurant.  
3. The system displays order details including customer name, dish, order type, assigned driver (if applicable), and order status. 

**Postcondition:** The manager obtains a complete overview of the restaurant’s orders.

---

### **Use Case Number: UC-06**

**Use Case Name:** Check Pending Deliveries  
**Overview:** Restaurant managers can specifically view orders that are pending delivery.  
**Actors:** Restaurant Manager, System  
**Precondition:** Manager is logged in and there are active delivery orders.  
**Flow:**

1. Manager selects "Check Pending Deliveries" from the management menu.  
2. The system retrieves only the delivery orders (where the order type is set to Delivery) for the restaurant.  
3. The system displays pending delivery orders with estimated remaining delivery times. 

**Postcondition:** The manager receives updated information on pending delivery orders.

---