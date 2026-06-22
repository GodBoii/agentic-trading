# Conditional Trigger API

The Conditional Trigger API is a special set of APIs that lets you place orders on the basis of set conditions. These conditions can be based on price, technical indicators, or a combination of both. You can set one or multiple orders to be triggered when the condition is met.

When the conditional order is triggered, you will receive a postback update if set up.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/alerts/orders` | Place Conditional Trigger |
| PUT | `/alerts/orders/{alertId}` | Modify Conditional Trigger |
| DELETE | `/alerts/orders/{alertId}` | Delete Conditional Trigger |
| GET | `/alerts/orders/{alertId}` | Get Conditional Trigger by ID |
| GET | `/alerts/orders` | Get All Conditional Triggers |

> **Note:**
> - Conditional Triggers are currently supported only for Equities and Indices.
> - You can receive a postback update by providing a Webhook URL while generating the Access Token.

---

## Place Conditional Trigger

Using this API, you can create a new conditional trigger by defining conditions (price or technical indicators) that, when met, place one or multiple orders automatically on the user's Dhan account. It supports multiple combinations of indicators and operators.

### Request

```bash
curl --request POST \
  --url https://api.dhan.co/v2/alerts/orders \
  --header 'Accept: application/json' \
  --header 'Content-Type: application/json' \
  --header 'access-token: JWT' \
  --data '{Request Body}'
```

### Request Structure

```json
{
  "dhanClientId": "123456789",
  "condition": {
    "comparisonType": "TECHNICAL_WITH_VALUE",
    "exchangeSegment": "NSE_EQ",
    "securityId": "12345",
    "indicatorName": "SMA_5",
    "timeFrame": "DAY",
    "operator": "CROSSING_UP",
    "comparingValue": 250,
    "expDate": "2019-08-24",
    "frequency": "ONCE",
    "userNote": "Price crossing SMA"
  },
  "orders": [
    {
      "transactionType": "BUY",
      "exchangeSegment": "NSE_EQ",
      "productType": "CNC",
      "orderType": "LIMIT",
      "securityId": "12345",
      "quantity": 10,
      "validity": "DAY",
      "price": "250.00",
      "discQuantity": "0",
      "triggerPrice": "0"
    }
  ]
}
```

### Request Parameters

| Parameter | Data Type | Description | Sample Value |
|---|---|---|---|
| `condition` *required* | object | Alert condition configuration | — |
| `condition.comparisonType` *required* | string | Type of comparison | `TECHNICAL_WITH_VALUE` |
| `condition.timeframe` *required* | string | Timeframe for indicator evaluation: `DATE`, `ONE_MIN`, `FIVE_MIN`, `FIFTEEN_MIN`, `DAY` | `DAY` |
| `condition.exchangeSegment` *required* | enum | Exchange where condition is evaluated: `NSE_EQ`, `BSE_EQ`, `IDX_I` | `NSE_EQ` |
| `condition.securityId` *required* | string | Exchange standard ID for each scrip | `12345` |
| `condition.indicatorName` *conditionally required* | string | Technical indicator name | `SMA_5` |
| `condition.operator` *required* | string | Condition Operator (e.g. `CROSSING_UP`, `CROSSING_DOWN`) | `CROSSING_UP` |
| `condition.comparingValue` *conditionally required* | number | Value with which indicator or price is compared | `250` |
| `condition.comparingIndicatorName` *conditionally required* | string | Technical indicator name | `SMA_10` |
| `condition.expDate` *required* | string (date) | Expiry date of alert (Default: 1 year) | `2019-08-24` |
| `condition.frequency` *required* | string | Trigger frequency (e.g. `ONCE`, `ALWAYS`) | `ONCE` |
| `condition.userNote` | string | User-provided note | `Price crossing SMA` |
| `orders` | array[object] | List of orders to execute when alert is triggered | — |
| `orders.transactionType` *required* | enum | The trading side of transaction: `BUY`, `SELL` | `BUY` |
| `orders.exchangeSegment` *required* | enum | Exchange Segment of instrument to be subscribed: `NSE_EQ` etc. | `NSE_EQ` |
| `orders.productType` *required* | enum | Product type: `CNC`, `INTRADAY`, `MARGIN`, `MTF` | `CNC` |
| `orders.orderType` *required* | enum | Order Type: `LIMIT`, `MARKET`, `STOP_LOSS`, `STOP_LOSS_MARKET` | `LIMIT` |
| `orders.securityId` *required* | string | Exchange standard ID for each scrip | `12345` |
| `orders.quantity` *required* | integer | Number of shares for the order | `10` |
| `orders.validity` *required* | enum | Validity of Order: `DAY`, `IOC` | `DAY` |
| `orders.price` *required* | string | Price at which order is placed | `250` |
| `orders.discQuantity` | string | Number of shares visible (Keep more than 30% of quantity) | `0` |
| `orders.triggerPrice` *conditionally required* | string | Price at which the order is triggered, in case of SL-M & SL-L | `0` |

### Response Structure

```json
{
  "alertId": "12345",
  "alertStatus": "ACTIVE"
}
```

### Response Parameters

| Parameter | Data Type | Description |
|---|---|---|
| `alertId` | string | Unique identifier of the created conditional trigger |
| `alertStatus` | string | Status of Conditional Trigger (e.g., `ACTIVE`, `INACTIVE`) |

---

## Modify Conditional Trigger

Modify an existing conditional trigger's logic and/or the associated order execution parameters.

### Request

```bash
curl --request PUT \
  --url https://api.dhan.co/v2/alerts/orders/{alertId} \
  --header 'Accept: application/json' \
  --header 'Content-Type: application/json' \
  --header 'access-token: JWT' \
  --data '{Request Body}'
```

### Request Structure

```json
{
  "dhanClientId": "123456789",
  "alertId": "12345",
  "condition": {
    "comparisonType": "TECHNICAL_WITH_VALUE",
    "exchangeSegment": "NSE_EQ",
    "securityId": "12345",
    "indicatorName": "SMA_5",
    "timeFrame": "DAY",
    "operator": "CROSSING_UP",
    "comparingValue": "250.00",
    "expDate": "2019-08-24",
    "frequency": "ONCE",
    "userNote": "Updated alert condition"
  },
  "orders": [
    {
      "transactionType": "BUY",
      "exchangeSegment": "NSE_EQ",
      "productType": "CNC",
      "orderType": "LIMIT",
      "securityId": "12345",
      "quantity": 10,
      "validity": "DAY",
      "price": "250.00",
      "discQuantity": "0",
      "triggerPrice": "0"
    }
  ]
}
```

### Request Parameters

| Parameter | Data Type | Description | Sample Value |
|---|---|---|---|
| `alertId` | string | Unique identifier of the alert to modify | `12345` |
| `condition` *required* | object | Alert condition configuration | — |
| `condition.comparisonType` *required* | string | Type of comparison | `TECHNICAL_WITH_VALUE` |
| `condition.timeframe` *required* | string | Timeframe for indicator evaluation: `DATE`, `ONE_MIN`, `FIVE_MIN`, `FIFTEEN_MIN`, `DAY` | `DAY` |
| `condition.exchangeSegment` *required* | enum | Exchange where condition is evaluated: `NSE_EQ`, `BSE_EQ`, `IDX_I` | `NSE_EQ` |
| `condition.securityId` *required* | string | Exchange standard ID for each scrip | `12345` |
| `condition.indicatorName` *conditionally required* | string | Technical indicator name | `SMA_5` |
| `condition.operator` *required* | string | Condition Operator | `CROSSING_UP` |
| `condition.comparingValue` *conditionally required* | number | Value with which indicator or price is compared | `250` |
| `condition.comparingIndicatorName` *conditionally required* | string | Technical indicator name | `SMA_10` |
| `condition.expDate` *required* | string (date) | Expiry date of alert | `2019-08-24` |
| `condition.frequency` *required* | string | Trigger frequency | `ONCE` |
| `condition.userNote` | string | User-provided note | `Updated alert condition` |
| `orders` | array[object] | List of orders to execute when alert is triggered | — |
| `orders.transactionType` | enum | The trading side of transaction: `BUY`, `SELL` | `BUY` |
| `orders.exchangeSegment` | enum | Exchange Segment of instrument to be subscribed | `NSE_EQ` |
| `orders.productType` | enum | Product type | `CNC` |
| `orders.orderType` | enum | Order Type | `LIMIT` |
| `orders.securityId` | string | Exchange standard ID for each scrip | `12345` |
| `orders.quantity` | integer | Number of shares for the order | `10` |
| `orders.validity` | enum | Validity of Order | `DAY` |
| `orders.price` | string | Price at which order is placed | `250` |
| `orders.discQuantity` | string | Number of shares visible | `0` |
| `orders.triggerPrice` | string | Price at which the order is triggered, in case of SL-M & SL-L | `0` |

---

## Delete Conditional Trigger

Delete an existing conditional trigger using its unique identifier (`alertId`).

### Request

```bash
curl --request DELETE \
  --url https://api.dhan.co/v2/alerts/orders/{alertId} \
  --header 'Accept: application/json' \
  --header 'access-token: JWT'
```

### Request Structure
*No Body*

### Response Structure

```json
{
  "alertId": "12345",
  "alertStatus": "CANCELLED"
}
```

### Response Parameters

| Parameter | Data Type | Description |
|---|---|---|
| `alertId` | string | Unique identifier of the alert |
| `alertStatus` | string | Status of the alert (e.g. `CANCELLED`) |

---

## Get Conditional Trigger by ID

Retrieve the status and detailed configuration for a specific trigger by its unique identification (`alertId`).

### Request

```bash
curl --request GET \
  --url https://api.dhan.co/v2/alerts/orders/{alertId} \
  --header 'Accept: application/json' \
  --header 'access-token: JWT'
```

### Request Structure
*No Body*

### Response Structure

```json
{
  "alertId": "12345",
  "alertStatus": "ACTIVE",
  "createdTime": "2019-08-24T14:15:22Z",
  "triggeredTime": null,
  "lastPrice": "245.50",
  "condition": {
    "comparisonType": "TECHNICAL_WITH_VALUE",
    "exchangeSegment": "NSE_EQ",
    "securityId": "12345",
    "indicatorName": "SMA_5",
    "timeFrame": "DAY",
    "operator": "CROSSING_UP",
    "comparingValue": "250.00",
    "expDate": "2019-08-24",
    "frequency": "ONCE",
    "userNote": "Price crossing SMA"
  },
  "orders": [
    {
      "transactionType": "BUY",
      "exchangeSegment": "NSE_EQ",
      "productType": "CNC",
      "orderType": "LIMIT",
      "securityId": "12345",
      "quantity": 10,
      "validity": "DAY",
      "price": "250.00",
      "discQuantity": "0",
      "triggerPrice": "0"
    }
  ]
}
```

### Response Parameters

| Parameter | Data Type | Description | Sample Value |
|---|---|---|---|
| `alertId` | string | Unique identifier of the alert | `12345` |
| `alertStatus` | string | Status of the alert | `ACTIVE` |
| `createdTime` | string | Timestamp when alert was created | `2019-08-24T14:15:22Z` |
| `triggeredTime` | string | Timestamp when alert was triggered | `2019-08-25T14:15:22Z` |
| `lastPrice` | string | Last price of the instrument | `245.50` |
| `condition` | object | Alert condition configuration | — |
| `condition.comparisonType` | string | Type of comparison | `TECHNICAL_WITH_VALUE` |
| `condition.timeframe` | string | Timeframe for indicator evaluation | `DAY` |
| `condition.exchangeSegment` | enum | Exchange where condition is evaluated | `NSE_EQ` |
| `condition.securityId` | string | Exchange standard ID for each scrip | `12345` |
| `condition.indicatorName` | string | Technical indicator name | `SMA_5` |
| `condition.operator` | string | Condition Operator | `CROSSING_UP` |
| `condition.comparingValue` | number | Value with which indicator or price is compared | `250` |
| `condition.comparingIndicatorName` | string | Technical indicator name | `SMA_10` |
| `condition.expDate` | string (date) | Expiry date of alert | `2019-08-24` |
| `condition.frequency` | string | Trigger frequency | `ONCE` |
| `condition.userNote` | string | User-provided note | `Price crossing SMA` |
| `orders` | array[object] | List of orders to execute when alert is triggered | — |
| `orders.transactionType` | enum | The trading side of transaction | `BUY` |
| `orders.exchangeSegment` | enum | Exchange Segment of instrument to be subscribed | `NSE_EQ` |
| `orders.productType` | enum | Product type | `CNC` |
| `orders.orderType` | enum | Order Type | `LIMIT` |
| `orders.securityId` | string | Exchange standard ID for each scrip | `12345` |
| `orders.quantity` | integer | Number of shares for the order | `10` |
| `orders.validity` | enum | Validity of Order | `DAY` |
| `orders.price` | string | Price at which order is placed | `250` |
| `orders.discQuantity` | string | Number of shares visible | `0` |
| `orders.triggerPrice` | string | Price at which the order is triggered | `0` |

---

## Get All Conditional Triggers

Retrieve a list of all conditional triggers for the authenticated account, along with their current status and configuration details.

### Request

```bash
curl --request GET \
  --url https://api.dhan.co/v2/alerts/orders \
  --header 'Accept: application/json' \
  --header 'access-token: JWT'
```

### Request Structure
*No Body*

### Response Structure

```json
[
  {
    "alertId": "12345",
    "alertStatus": "ACTIVE",
    "createdTime": "2019-08-24T14:15:22Z",
    "triggeredTime": null,
    "lastPrice": 245.5,
    "condition": {
      "comparisonType": "TECHNICAL_WITH_VALUE",
      "exchangeSegment": "NSE_EQ",
      "securityId": "12345",
      "indicatorName": "SMA_5",
      "timeFrame": "DAY",
      "operator": "CROSSING_UP",
      "comparingValue": 250,
      "expDate": "2019-08-24",
      "frequency": "ONCE",
      "userNote": "Price crossing SMA"
    },
    "orders": [
      {
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "CNC",
        "orderType": "LIMIT",
        "securityId": "12345",
        "quantity": 10,
        "validity": "DAY",
        "price": "250.00",
        "discQuantity": "0",
        "triggerPrice": "0"
      }
    ]
  }
]
```

### Response Parameters
Same structure as **Get Conditional Trigger by ID** response parameters (returned as a list).

---

**Note:** For description of enum values, refer [Annexure](https://dhanhq.co/docs/v2/annexure)
