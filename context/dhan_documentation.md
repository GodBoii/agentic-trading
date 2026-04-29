Now let me compile all the documentation into a comprehensive markdown format:

# DhanHQ API v2.0 - Complete Documentation

## Getting Started

![intro](https://dhanhq.co/docs/v2/img/intro.svg)

DhanHQ API is a state-of-the-art platform for you to build trading and investment services & strategies.

It is a set of REST-like APIs that provide integration with our trading platform. Execute & modify orders in real time, manage portfolio, access live market data and more, with lightning fast API collection.

We offer resource-based URLs that accept JSON or form-encoded requests. The response is returned as JSON-encoded responses by using Standard HTTP response codes, verbs, and authentication.

![sandbox](https://dhanhq.co/docs/v2/img/btn2sandbox.png)
**Developer Kit**

![python](https://dhanhq.co/docs/v2/img/btn2pydhanhq.png)
**DhanHQ Python Client**

## Structure

### REST
All GET and DELETE request parameters go as query parameters, and POST and PUT parameters as form-encoded. User has to input an access token in the header for every request.

```bash
curl --request POST \
--url https://api.dhan.co/v2/ \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{Request JSON}'
```

### Python
Install Python Package directly using following command in command line.

```bash
pip install dhanhq
```

This installs entire DhanHQ Python Client along with the required packages. Now, you can start using DhanHQ Client with your Python script.

You can now import 'dhanhq' module and connect to your Dhan account.

```python
from dhanhq import dhanhq

dhan = dhanhq("client_id","access_token")
```

## Errors

Error responses come with the error code and message generated internally by the system. The sample structure of error response is shown below.

```json
{
    "errorType": "",
    "errorCode": "",
    "errorMessage": ""
}
```

You can find detailed error code and message under [Annexure](#trading-api-error).

## Rate Limit

| Rate Limit | Order APIs | Data APIs | Quote APIs | Non Trading APIs |
|------------|------------|-----------|------------|------------------|
| per second | 25 | 5 | 1 | 20 |
| per minute | 250 | - | Unlimited | Unlimited |
| per hour | 1000 | - | Unlimited | Unlimited |
| per day | 7000 | 100000 | Unlimited | Unlimited |

Order Modifications are capped at 25 modifications/order

---

## Authentication

DhanHQ APIs require authentication based on an access token which needs to be passed with every request. There are various different methods to generate this access token depending on user type and the purpose of usage.

There are two categories in which users of DhanHQ APIs are divided:

- **Individual** - Users who have Dhan account and are coders, traders, geeks who want to build their own algorithm or trading system on top of DhanHQ APIs
- **Partners** - Platforms who want to build on top of DhanHQ APIs and serve it to their users. This can be algo platforms, fintechs, banks, PMS, and others.

### Eligibility

All Dhan users get access to Trading APIs for free. This means you can place and manage orders, positions, funds and all other transactions without paying any extra charges. For Data APIs, there are additional charges which are mentioned on the platform.

If you are a partner who wants to get integrated and build on top of DhanHQ APIs, you can reach out to us by filling form on the DhanHQ website [here](https://dhanhq.co/trading-apis). We are looking forward to build the ecosystem around DhanHQ APIs.

### Getting Started

#### For Individual Traders

As an individual trader, there are two methods using which a user can generate an access token:

- Directly generate access token from Dhan Web
- Use API key based authentication method

##### Access Token

Individual traders can directly get their Access Token from [web.dhan.co](https://web.dhan.co/). All Dhan users are eligible to get free access to Trading APIs. Here's how to get your Access Token:

- Login to [web.dhan.co](https://web.dhan.co/)
- Click on My Profile and navigate to **'Access DhanHQ APIs'**
- Generate "Access Token" for a validity of 24 hours from there.
- User have an option to enter Postback URL while generating the access token, to get order updates as [Postback](https://dhanhq.co/postback/).

**Refresh Access Token**

You can refresh your token for 24 hours with this endpoint:

```bash
curl --location 'https://api.dhan.co/v2/RenewToken' \
--header 'access-token: {JWT Token}' \
--header 'dhanClientId: {Client ID}'
```

This expires your current token and provides you with a new token with another 24 hours of validity.

##### API key & secret

Individuals can login with an OAuth based flow as well. All dhan users can generate individual user specific API key and secret. To generate API key and secret, a user needs to follow the below steps:

- Login to [web.dhan.co](https://web.dhan.co/)
- Click on My Profile and navigate to **'Access DhanHQ APIs'**
- Toggle to **'API key'** and enter your app name
- Enter **App name**, **Redirect URL** (to be used at the end of Step 2 provided below) and **Postback URL** (which is option to get updates on [Postback](https://dhanhq.co/postback/)).

**Note:** API Key & Secret are valid for 12 months from the date of generation

After getting the API key and secret, user needs to follow below three steps, in order to generate access token, which can be used for all other API authentication.

**STEP 1: Generate Consent**

This API is provided to generate consent to initiate a login session. On this step, the App ID and secret is validated and a new session is created for the user to enter credentials.

```bash
curl --location --request POST 'https://auth.dhan.co/app/generate-consent?client_id={dhanClientId}' \
--header 'app_id: {API key}' \
--header 'app_secret: {API secret}'
```

The response of this flow will have `consentAppId`. This `consentAppId` will be required for the next step of browser based flow.

**Note:** User can generate upto 25 `consentAppId` in a day. Each consent app ID stay active until tokenId is generated for them. However, at any given point of time, only one token will be generated.

**Header**

| Field | Description |
|-------|-------------|
| app_id _required_ | API Key generated from Dhan |
| app_secret _required_ | API Secret generated from Dhan |

**Response Structure**

```json
{
    "consentAppId": "940b0ca1-3ff4-4476-b46e-03a3ce7dc55d",
    "consentAppStatus": "GENERATED",
    "status": "success"
}
```

**Parameters**

| Field | Description |
|-------|-------------|
| consentAppId | Temporary session ID, to be used in step 2 |
| consentAppStatus | Status of the API request |

**STEP 2: Browser based login**

This endpoint needs to be opened directly on a browser. On this step, the user needs to enter their Dhan credentials, validate with 2FA like OTP/pin/password. If the login is successful, the user is redirected to the URL provided while generating the API key. Along with the redirect, we also send `tokenId` which needs to be used in step 3.

**Note:** This will end up with a 302 redirect on the browser. You can consume the `tokenId` from the path parameter directly.

**Request URL**

```
https://auth.dhan.co/login/consentApp-login?consentAppId={consentAppId}
```

**Path Parameter**

| Field | Description |
|-------|-------------|
| consentAppId _required_ | Temporary session ID created in Generate Consent (I) stage |

**Response Structure**

```
{redirect_URL}/?tokenId={Token ID for user}
```

**Parameters**

| Field | Description |
|-------|-------------|
| tokenId | Token ID to be used to generate Access Token |

**STEP 3: Consume Consent**

This API is to generate access token by validating API key & secret and using `tokenId` generated in the above step. This results in the `access token` which needs to be used in all other API endpoints.

```bash
curl --location 'https://auth.dhan.co/app/consumeApp-consent?tokenId={Token ID}' \
--header 'app_id: {API Key}' \
--header 'app_secret: {API Secret}'
```

**Path Parameter**

| Field | Description |
|-------|-------------|
| tokenId _required_ | User specific token ID, obtained in stage II |

**Header**

| Field | Description |
|-------|-------------|
| app_id _required_ | API Key generated from Dhan |
| app_secret _required_ | API Secret generated from Dhan |

**Response Structure**

```json
{
    "dhanClientId": "1000000001",
    "dhanClientName": "JOHN DOE",
    "dhanClientUcc": "CEFE4265",
    "givenPowerOfAttorney": true,
    "accessToken": "{access token}",
    "expiryTime": "2025-09-23T12:37:23"
}
```

**Parameters**

| Field | Description |
|-------|-------------|
| dhanClientId | User specific identification generated by Dhan |
| dhanClientName | Name of the User |
| dhanClientUcc | Unique Client Code (UCC) |
| givenPowerOfAttorney | Whether the user has activated DDPI (true/false) |
| accessToken | JWT access token to be used for API authentication |
| expiryTime | ISO timestamp when the access token expires as per IST |

#### For Partners

Once partner receives `partner_id` & `partner_secret`, they can use this authentication mechanism for their users.

This login method is a three step based, which is outlined below. This is for all different types of platforms, wherein the user can login to their Dhan account right from the third party platform itself.

**STEP 1: Generate Consent**

This API is to generate consent to initiate a login session for a user. This is to validate the partner and allow them to start the authentication process.

```bash
curl --location 'https://auth.dhan.co/partner/generate-consent' \
--header 'partner_id: {Partner ID}' \
--header 'partner_secret: {Partner Secret}'
```

The response of this flow will have `consentId`. This `consentId` can be used for the next browser based flow.

![01](https://dhanhq.co/docs/v2/img/01.png)

**Header**

| Field | Description |
|-------|-------------|
| partner_id _required_ | Partner ID provided by Dhan |
| partner_secret _required_ | Partner Secret provided by Dhan |

**Response Structure**

```json
{
    "consentId": "ab5aaab6-38cb-41fc-a074-c816e2f9a3e0",
    "consentStatus": "GENERATED"
}
```

**Parameters**

| Field | Description |
|-------|-------------|
| consentId | Temporary session ID on partner level, to be used in step 2 |

**STEP 2: Dhan login on browser for user**

This endpoint needs to be opened directly on a tab for browser based applications or on the webview for mobile apps. On this step, the end user needs to enter their Dhan credentials, validate with 2FA like OTP/pin/password. If the login is successful, the user is redirected to the URL provided to us. Along with the redirect, we also send `tokenId` which needs to be used in step 3.

![02](https://dev-images.dhan.co/common/02.png)

**Note:** This will end up with a 302 redirect on the browser. You can consume the `tokenId` from the path parameter directly.

**Request URL**

```
https://auth.dhan.co/consent-login?consentId={consentId}
```

**Path Parameter**

| Field | Description |
|-------|-------------|
| consentId _required_ | Temporary session ID created in Generate Consent (I) stage |

**Response Structure**

```
{redirect_URL}/?tokenId={Token ID for user}
```

**Parameters**

| Field | Description |
|-------|-------------|
| tokenId | Token ID to be used to generate Access Token |

**STEP 3: Consume Consent**

This API is to generate access token by validating partner credentials and using `tokenId` generated in the above step.

```bash
curl --location 'https://auth.dhan.co/partner/consume-consent?tokenId={Token ID}' \
--header 'partner_id: {Partner ID}' \
--header 'partner_secret: {Partner Secret}'
```

![03](https://dev-images.dhan.co/common/03.png)

**Path Parameter**

| Field | Description |
|-------|-------------|
| tokenId _required_ | User specific token ID, obtained in stage II |

**Header**

| Field | Description |
|-------|-------------|
| partner_id _required_ | Partner ID provided by Dhan |
| partner_secret _required_ | Partner Secret provided by Dhan |

**Response Structure**

```json
{
    "dhanClientId": "1000000001",
    "dhanClientName": "JOHN DOE",
    "dhanClientUcc": "CEFE4265",
    "givenPowerOfAttorney": true,
    "accessToken": "{access token}",
    "expiryTime": "2025-09-23T12:37:23"
}
```

**Parameters**

| Field | Description |
|-------|-------------|
| dhanClientId | User specific identification generated by Dhan |
| dhanClientName | Name of the User |
| dhanClientUcc | Unique Client Code (UCC) |
| givenPowerOfAttorney | Whether the user has activated DDPI (true/false) |
| accessToken | JWT access token to be used for API authentication |
| expiryTime | ISO timestamp when the access token expires as per IST |

### Setup Static IP

Static IP whitelisting is mandatory as per the new SEBI and exchange guidelines. In line with this, you can use the below APIs to set Static IP for your account. Alternatively, you can also use Dhan Web ([web.dhan.co](https://web.dhan.co/)) to setup your Static IP.

You can set up a primary and a secondary IP for your account. Do note that each individual needs to have a unique static IP. Once an IP is whitelisted, it cannot be edited for the next 7 days or as recommended by the exchange. Do note that Static IP is only required while using Order Placement APIs including Orders, Super Order, Forever Order. While fetching order details or trade details, no such IP whitelisting is required.

Below set of APIs can be used to manage Static IP for your account.

**Info:** A static IP is a fixed, permanent internet address for your device or server. Unlike the default IP you get on home Wi-Fi (which your ISP changes automatically from time to time), a static IP never changes. To use one, you need to request and purchase it separately from your Internet Service Provider (ISP).

#### Set IP

You can use this API to setup Primary and Secondary IP for your account. This supports both IPv4 and IPv6 formats while setting up.

Once an IP is setup, you cannot modify the same for the next 7 days.

```bash
curl --request POST \
--url https://api.dhan.co/v2/ip/setIP \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: {Access Token}' \
--data '{
"dhanClientId": "1000000001",
"ip": "10.200.10.10",
"ipFlag": "PRIMARY"
}'
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId _required_ | string | User specific identification generated by Dhan |
| ip _required_ | string | Static IP address in IPv4 or IPv6 format |
| ipFlag _required_ | string (enum) | Flag to set the IP as primary or secondary: `PRIMARY` `SECONDARY` |

**Response Structure**

```json
{
"message": "IP saved successfully",
"status": "SUCCESS"
}
```

**Parameters**

| Field | Description |
|-------|-------------|
| message | API response confirmation |
| status | Status of the request |

#### Modify IP

You can use this API to modify Primary and Secondary IP set for your account. This API can only be used in the period wherein IP modification is allowed, which is once every 7 days.

```bash
curl --request PUT \
--url https://api.dhan.co/v2/ip/modifyIP \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: {Access Token}' \
--data '{
"dhanClientId": "1000000001",
"ip": "10.200.10.10",
"ipFlag": "PRIMARY"
}'
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId _required_ | string | User specific identification generated by Dhan |
| ip _required_ | string | Static IP address in IPv4 or IPv6 format |
| ipFlag _required_ | string (enum) | Flag to set the IP as primary or secondary: `PRIMARY` `SECONDARY` |

**Response Structure**

```json
{
"message": "IP saved successfully",
"status": "SUCCESS"
}
```

**Parameters**

| Field | Description |
|-------|-------------|
| message | API response confirmation |
| status | Status of the request |

#### Get IP

This API is to get the list of currently set IPs - both primary and secondary along with the date when this IP will be allowed to be modified.

```bash
curl --request GET \
--url https://api.dhan.co/v2/ip/getIP \
--header 'Accept: application/json' \
--header 'access-token: {Access Token}'
```

This is a GET request, where in the `access-token` needs to be passed on header.

**Response Structure**

```json
{
    "modifyDateSecondary": "2025-09-30",
    "secondaryIP": "10.420.43.12",
    "modifyDatePrimary": "2025-09-28",
    "primaryIP": "10.420.29.14"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| modifyDateSecondary | string | Date from which the secondary IP can be modified (YYYY-MM-DD) |
| secondaryIP | string | Currently set secondary static IP (IPv4 or IPv6) |
| modifyDatePrimary | string | Date from which the primary IP can be modified (YYYY-MM-DD) |
| primaryIP | string | Currently set primary static IP (IPv4 or IPv6) |

### Setup TOTP

As an API user, you can setup TOTP to simplify authentication for API-only flows, as an alternative to enter OTP received on email or mobile number.

#### What is TOTP?

Time-based One-Time Password (TOTP) is a 6-digit code generated from a shared secret and current time (RFC 6238). Once you enable TOTP for your account, you'll receive a secret (via QR/code) that your server can use to generate a fresh code every 30 seconds.

#### How to set up TOTP

1. Go to Dhan Web > DhanHQ Trading APIs section
2. Select Setup TOTP
3. Confirm with OTP on mobile/email
4. Scan the QR via an Authenticator app or enter the code shown into the Authenticator
5. Confirm by entering the first TOTP

Once this is is setup, you will by default see TOTP as an option while logging into any partner platforms or inside the API key based authentication mode.

### User Profile

User Profile API can be used to check validity of access token and account setup. It is a simple GET request and can be a great test API for you to start integration.

```bash
curl --location 'https://api.dhan.co/v2/profile' \
--header 'access-token: {JWT}'
```

**Response Structure**

```json
{
    "dhanClientId": "1100003626",
    "tokenValidity": "30/03/2025 15:37",
    "activeSegment": "Equity, Derivative, Currency, Commodity",
    "ddpi": "Active",
    "mtf": "Active",
    "dataPlan": "Active",
    "dataValidity": "2024-12-05 09:37:52.0"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| tokenValidity | string | Validity date and time for Token |
| activeSegment | string | All active segments in user accounts |
| ddpi | string | DDPI status of the user: `Active` `Deactive` |
| mtf | string | MTF consent status of the user: `Active` `Deactive` |
| dataPlan | string | Data API subscription status: `Active` `Deactive` |
| dataValidity | string | Validity date and time for Data API Subscription |

---

## Orders

The order management API lets you place a new order, cancel or modify the pending order, retrieve the order status, trade status, order book & tradebook.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /orders | Place a new order |
| PUT | /orders/{order-id} | Modify a pending order |
| DELETE | /orders/{order-id} | Cancel a pending order |
| POST | /orders/slicing | Slice order into multiple legs over freeze limit |
| GET | /orders | Retrieve the list of all orders for the day |
| GET | /orders/{order-id} | Retrieve the status of an order |
| GET | /orders/external/{correlation-id} | Retrieve the status of an order by correlation id |
| GET | /trades | Retrieve the list of all trades for the day |
| GET | /trades/{order-id} | Retrieve the details of trade by an order id |

**Note:** Order Placement, Modification and Cancellation APIs requires Static IP whitelisting - [here](#setup-static-ip)

### Order Placement

The order request API lets you place new orders.

```bash
curl --request POST \
--url https://api.dhan.co/v2/orders \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{Request JSON}'
```

**Request Structure**

```json
{
    "dhanClientId":"1000000003",
    "correlationId":"123abc678",
    "transactionType":"BUY",
    "exchangeSegment":"NSE_EQ",
    "productType":"INTRADAY",
    "orderType":"MARKET",
    "validity":"DAY",
    "securityId":"11536",
    "quantity":"5",
    "disclosedQuantity":"",
    "price":"",
    "triggerPrice":"",
    "afterMarketOrder":false,
    "amoTime":"",
    "boProfitValue":"",
    "boStopLossValue": ""
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId _required_ | string | User specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back. |
| transactionType _required_ | enum string | The trading side of transaction: `BUY` `SELL` |
| exchangeSegment _required_ | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](#exchange-segment) |
| productType _required_ | enum string | Product type: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| orderType _required_ | enum string | Order Type: `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| validity _required_ | enum string | Validity of Order: `DAY` `IOC` |
| securityId _required_ | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| quantity _required_ | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible (Keep more than 30% of quantity) |
| price _required_ | float | Price at which order is placed |
| triggerPrice _conditionally required_ | float | Price at which the order is triggered, in case of SL-M & SL-L |
| afterMarketOrder _conditionally required_ | boolean | Flag for orders placed after market hours |
| amoTime _conditionally required_ | enum string | Timing to pump the after market order: `PRE_OPEN` `OPEN` `OPEN_30` `OPEN_60` |
| boProfitValue _conditionally required_ | float | Bracket Order Target Price change |
| boStopLossValue _conditionally required_ | float | Bracket Order Stop Loss Price change |

**Response Structure**

```json
{
    "orderId": "112111182198",
    "orderStatus": "PENDING"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order: `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |

### Order Modification

Using this API one can modify pending order in orderbook. The variables that can be modified are price, quantity, order type & validity. The user has to mention the desired value in fields.

```bash
curl --request PUT \
--url https://api.dhan.co/v2/orders/{order-id} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{Request JSON}'
```

**Request Structure**

```json
{
    "dhanClientId":"1000000009",
    "orderId":"112111182045",
    "orderType":"LIMIT",
    "legName":"",
    "quantity":"40",
    "price":"3345.8",
    "disclosedQuantity":"10",
    "triggerPrice":"",
    "validity":"DAY"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId _required_ | string | User specific identification generated by Dhan |
| orderId _required_ | string | Order specific identification generated by Dhan |
| orderType _required_ | enum string | Order Type: `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| legName _conditionally required_ | enum string | In case of BO & CO, which leg is modified: `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| quantity _conditionally required_ | int | Quantity to be modified |
| price _conditionally required_ | float | Price to be modified |
| disclosedQuantity | int | Number of shares visible (if opting keep >30% of quantity) |
| triggerPrice _conditionally required_ | float | Price at which the order is triggered, in case of SL-M & SL-L |
| validity _required_ | enum string | Validity of Order: `DAY` `IOC` |

**Response Structure**

```json
{
    "orderId": "112111182045",
    "orderStatus": "TRANSIT"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order: `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |

### Order Cancellation

Users can cancel a pending order in the orderbook using the order id of an order. There is no body for request and response for this call. On successful completion of request 202 Accepted response status code will appear.

```bash
curl --request DELETE \
--url https://api.dhan.co/v2/orders/{order-id} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

```json
{
"orderId": "112111182045",
"orderStatus": "CANCELLED"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | enum string | Last updated status of the order: `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` |

### Order Slicing

This API helps you slice your order request into multiple orders to allow you to place over freeze limit quantity for F&O instruments.

```bash
curl --request POST \
--url https://api.dhan.co/v2/orders/slicing \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
--data '{Request JSON}'
```

**Request Structure**

```json
{
    "dhanClientId":"1000000003",
    "correlationId":"123abc678",
    "transactionType":"BUY",
    "exchangeSegment":"NSE_EQ",
    "productType":"INTRADAY",
    "orderType":"MARKET",
    "validity":"DAY",
    "securityId":"11536",
    "quantity":"5",
    "disclosedQuantity":"",
    "price":"",
    "triggerPrice":"",
    "afterMarketOrder":false,
    "amoTime":"",
    "boProfitValue":"",
    "boStopLossValue": ""
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId _required_ | string | User specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back. |
| transactionType _required_ | enum string | The trading side of transaction: `BUY` `SELL` |
| exchangeSegment _required_ | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](#exchange-segment) |
| productType _required_ | enum string | Product type: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| orderType _required_ | enum string | Order Type: `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| validity _required_ | enum string | Validity of Order: `DAY` `IOC` |
| securityId _required_ | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| quantity _required_ | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible (Keep more than 30% of quantity) |
| price _required_ | float | Price at which order is placed |
| triggerPrice _conditionally required_ | float | Price at which the order is triggered, in case of SL-M & SL-L |
| afterMarketOrder _conditionally required_ | boolean | Flag for orders placed after market hours |
| amoTime _conditionally required_ | enum string | Timing to pump the after market order: `PRE_OPEN` `OPEN` `OPEN_30` `OPEN_60` |
| boProfitValue _conditionally required_ | float | Bracket Order Target Price change |
| boStopLossValue _conditionally required_ | float | Bracket Order Stop Loss Price change |

**Response Structure**

```json
[
    {
        "orderId": "552209237100",
        "orderStatus": "TRANSIT"
    },
    {
        "orderId": "552209237100",
        "orderStatus": "TRANSIT"
    }
]
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| orderId | string | Order specific identification generated by Dhan |
| orderStatus | string | Order Type: `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `TRADED` `EXPIRED` `CONFIRM` |

### Order Book

This API lets you retrieve an array of all orders requested in a day with their last updated status.

```bash
curl --request GET \
--url https://api.dhan.co/v2/orders \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

```json
[
    {
        "dhanClientId": "1000000003",
        "orderId": "112111182198",
        "correlationId":"123abc678",
        "orderStatus": "PENDING",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "tradingSymbol": "",
        "securityId": "11536",
        "quantity": 5,
        "disclosedQuantity": 0,
        "price": 0.0,
        "triggerPrice": 0.0,
        "afterMarketOrder": false,
        "boProfitValue": 0.0,
        "boStopLossValue": 0.0,
        "legName": ,
        "createTime": "2021-11-24 13:33:03",
        "updateTime": "2021-11-24 13:33:03",
        "exchangeTime": "2021-11-24 13:33:03",
        "drvExpiryDate": null,
        "drvOptionType": null,
        "drvStrikePrice": 0.0,
        "omsErrorCode": null,
        "omsErrorDescription": null,
        "algoId": "string",
        "remainingQuantity": 5,
        "averageTradedPrice": 0,
        "filledQty": 0
    }
]
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| correlationId | string | The user/partner generated id for tracking back |
| orderStatus | enum string | Last updated status of the order: `TRANSIT` `PENDING` `REJECTED` `CANCELLED` `PART_TRADED` `TRADED` `EXPIRED` |
| transactionType | enum string | The trading side of transaction: `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](#exchange-segment) |
| productType | enum string | Product type of trade: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| orderType | enum string | Order Type: `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| validity | enum string | Validity of Order: `DAY` `IOC` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| quantity | int | Number of shares for the order |
| disclosedQuantity | int | Number of shares visible |
| price | float | Price at which order is placed |
| triggerPrice | float | Price at which order is triggered, for SL-M, SL-L, CO & BO |
| afterMarketOrder | boolean | The order placed is AMO ? |
| boProfitValue | float | Bracket Order Target Price change |
| boStopLossValue | float | Bracket Order Stop Loss Price change |
| legName | enum string | Leg identification in case of BO: `ENTRY_LEG` `TARGET_LEG` `STOP_LOSS_LEG` |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | int | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option: `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| omsErrorCode | string | Error code in case the order is rejected or failed |
| omsErrorDescription | string | Description of error in case the order is rejected or failed |
| algoId | string | Exchange Algo ID for Dhan |
| remainingQuantity | integer | Quantity pending at the exchange to be traded (quantity - filledQty) |
| averageTradedPrice | integer | Average price at which order is traded |
| filledQty | integer | Quantity of order traded on Exchange |

### Get Order by Order Id

Users can retrieve the details and status of an order from the orderbook placed during the day.

```bash
curl --request GET \
--url https://api.dhan.co/v2/orders/{order-id} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

Same as Order Book response (single object instead of array)

### Get Order by Correlation Id

In case the user has missed order id due to unforeseen reason, this API retrieves the order status using a tag called correlation id specified by users themselve.

```bash
curl --request GET \
--url https://api.dhan.co/v2/orders/external/{correlation-id} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

Same as Order Book response (single object instead of array)

### Trade Book

This API lets you retrieve an array of all trades executed in a day.

```bash
curl --request GET \
--url https://api.dhan.co/v2/trades \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

```json
[
    {
        "dhanClientId": "1000000009",
        "orderId": "112111182045",
        "exchangeOrderId": "15112111182045",
        "exchangeTradeId": "15112111182045",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_EQ",
        "productType": "INTRADAY",
        "orderType": "LIMIT",
        "tradingSymbol": "TCS",
        "securityId": "11536",
        "tradedQuantity": 40,
        "tradedPrice": 3345.8,
        "createTime": "2021-03-10 11:20:06",
        "updateTime": "2021-11-25 17:35:12",
        "exchangeTime": "2021-11-25 17:35:12",
        "drvExpiryDate": null,
        "drvOptionType": null,
        "drvStrikePrice": 0.0
    }
]
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| exchangeOrderId | string | Order specific identification generated by exchange |
| exchangeTradeId | string | Trade specific identification generated by exchange |
| transactionType | enum string | The trading side of transaction: `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](#exchange-segment) |
| productType | enum string | Product type of trade: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| orderType | enum string | Order Type: `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| tradedQuantity | int | Number of shares executed |
| tradedPrice | float | Price at which trade is executed |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | int | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option: `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |

### Trades of an Order

Users can retrieve the trade details using an order id. Often during partial trades or Bracket/ Cover Orders, traders get confused in reading trade from tradebook. The response of this API will include all the trades generated for a particular order id.

```bash
curl --request GET \
--url https://api.dhan.co/v2/trades/{order-id} \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

Same as Trade Book response (single object instead of array)

**Note:** For description of enum values, refer [Annexure](#annexure)

---

## Portfolio

This API lets you retrieve holdings and positions in your portfolio.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /holdings | Retrieve list of holdings in demat account |
| GET | /positions | Retrieve open positions |
| POST | /positions/convert | Convert intraday position to delivery or delivery to intraday |

### Holdings

Users can retrieve all holdings bought/sold in previous trading sessions. All T1 and delivered quantities can be fetched.

```bash
curl --request GET \
--url https://api.dhan.co/v2/holdings \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

```json
[
    {
    "exchange": "ALL",
    "tradingSymbol": "HDFC",
    "securityId": "1330",
    "isin": "INE001A01036",
    "totalQty": 1000,
    "dpQty": 1000,
    "t1Qty": 0,
    "availableQty": 1000,
    "collateralQty": 0,
    "avgCostPrice": 2655.0
    } 
]
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| exchange | enum string | Exchange |
| tradingSymbol | string | Refer Trading Symbol at Page No |
| securityId | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| isin | string | Universal standard ID for each scrip |
| totalQty | int | Total quantity |
| dpQty | int | Quantity delivered in demat account |
| t1Qty | int | Quantity pending delivered in demat account |
| availableQty | int | Quantity available for transaction |
| collateralQty | int | Quantity placed as collateral with broker |
| avgCostPrice | float | Average Buy Price of total quantity |

### Positions

Users can retrieve a list of all open positions for the day. This includes all F&O carryforward positions as well.

```bash
curl --request GET \
--url https://api.dhan.co/v2/positions \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

```json
[
    {
    "dhanClientId": "1000000009",    
    "tradingSymbol": "TCS",
    "securityId": "11536",
    "positionType": "LONG",
    "exchangeSegment": "NSE_EQ", 
    "productType": "CNC",
    "buyAvg": 3345.8,
    "buyQty": 40,
    "costPrice": 3215.0,
    "sellAvg": 0.0,
    "sellQty": 0,
    "netQty": 40,
    "realizedProfit": 0.0,
    "unrealizedProfit": 6122.0,
    "rbiReferenceRate": 1.0,
    "multiplier": 1,
    "carryForwardBuyQty": 0,
    "carryForwardSellQty": 0,
    "carryForwardBuyValue": 0.0,
    "carryForwardSellValue": 0.0,
    "dayBuyQty": 40,
    "daySellQty": 0,
    "dayBuyValue": 133832.0,
    "daySellValue": 0.0,
    "drvExpiryDate": "0001-01-01",
    "drvOptionType": null,
    "drvStrikePrice": 0.0,
    "crossCurrency": false
    } 
]
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| securityId | string | Exchange standard id for each scrip. Refer [here](#instruments) |
| positionType | enum string | Position Type: `LONG` `SHORT` `CLOSED` |
| exchangeSegment | enum string | Exchange & Segment: `NSE_EQ` `NSE_FNO` `NSE_CURRENCY` `BSE_EQ` `BSE_FNO` `BSE_CURRENCY` `MCX_COMM` |
| productType | enum string | Product type: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| buyAvg | float | Average buy price mark to market |
| buyQty | int | Total quantity bought |
| costPrice | int | Actual Cost Price |
| sellAvg | float | Average sell price mark to market |
| sellQty | int | Total quantities sold |
| netQty | int | buyQty - sellQty = netQty |
| realizedProfit | float | Profit or loss booked |
| unrealizedProfit | float | Profit or loss standing for open position |
| rbiReferenceRate | float | RBI mandated reference rate for forex |
| multiplier | int | Multiplying factor for currency F&O |
| carryForwardBuyQty | int | Carry forward F&O long quantities |
| carryForwardSellQty | int | Carry forward F&O short quantities |
| carryForwardBuyValue | float | Carry forward F&O long value |
| carryForwardSellValue | float | Carry forward F&O short value |
| dayBuyQty | int | Quantities bought today |
| daySellQty | int | Quantities sold today |
| dayBuyValue | float | Value of quantities bought today |
| daySellValue | float | Value of quantities sold today |
| drvExpiryDate | int | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option: `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |
| crossCurrency | boolean | Check for non INR currency pair |

### Convert Position

Users can convert their open position from intraday to delivery or delivery to intraday.

```bash
curl --request POST \
--url https://api.dhan.co/v2/positions/convert \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{}'
```

**Request Structure**

```json
{
    "dhanClientId": "1000000009",
    "fromProductType":"INTRADAY",  
    "exchangeSegment":"NSE_EQ",
    "positionType":"LONG",
    "securityId":"11536",  
    "tradingSymbol":"",
    "convertQty":"40",
    "toProductType":"CNC"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| fromProductType | enum string | Refer Trading Symbol in Tables: `CNC` `INTRADAY` `MARGIN` `CO` `BO` |
| exchangeSegment | enum string | Exchange & segment in which position is created - [here](#exchange-segment) |
| positionType | enum string | Position Type: `LONG` `SHORT` `CLOSED` |
| securityId | string | Exchange standard id for each scrip. Refer [here](#instruments) |
| tradingSymbol | string | Refer Trading Symbol in Tables |
| convertQty | int | No of shares modification is desired |
| toProductType | enum string | Desired product type: `CNC` `INTRADAY` `MARGIN` `CO` `BO` |

**Response Structure**

```
202 Accepted
```

**Note:** For description of enum values, refer [Annexure](#annexure)

---

## Funds

Users can get details about the fund requirements or available funds (with margin requirements) in their Trading Account.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /margincalculator | Margin requirement for any order |
| GET | /fundlimit | Retrieve trading account fund information |

### Margin Calculator

Fetch span, exposure, var, brokerage, leverage, available margin values for any type of order and instrument that you want to place.

```bash
curl --request POST \
--url https://api.dhan.co/v2/margincalculator \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: ' \
--data '{Request JSON}'
```

**Request Structure**

```json
{
    "dhanClientId": "1000000132",
    "exchangeSegment": "NSE_EQ",
    "transactionType": "BUY",
    "quantity": 5,
    "productType": "CNC",
    "securityId": "1333",
    "price": 1428,
    "triggerPrice": 1427
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId _required_ | string | User specific identification generated by Dhan |
| exchangeSegment _required_ | enum string | Exchange & Segment: `NSE_EQ` `NSE_FNO` `BSE_EQ` `BSE_FNO` `MCX_COMM` |
| transactionType _required_ | enum string | The trading side of transaction: `BUY` `SELL` |
| quantity _required_ | int | Number of shares for the order |
| productType _required_ | enum string | Product type: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| securityId _required_ | string | Exchange standard id for each scrip. Refer [here](#instruments) |
| price _required_ | float | Price at which order is placed |
| triggerPrice _conditionally required_ | float | Price at which the order is triggered, in case of SL-M & SL-L |

**Response Structure**

```json
{
    "totalMargin": 2800.00,
    "spanMargin": 1200.00,
    "exposureMargin": 1003.00,
    "availableBalance": 10500.00,
    "variableMargin": 1000.00,
    "insufficientBalance": 0.00,
    "brokerage": 20.00,
    "leverage": "4.00"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| totalMargin | float | Total Margin required for placing the order successfully |
| spanMargin | float | SPAN margin required |
| exposureMargin | float | Exposure margin required |
| availableBalance | float | Available amount in trading account |
| variableMargin | float | VAR or Variable margin required |
| insufficientBalance | float | Insufficient amount in trading account (Available Balance - Total Margin) |
| brokerage | float | Brokerage charges for executing order |
| leverage | string | Margin leverage provided for the order as per product type |

### Fund Limit

Get all information of your trading account like balance, margin utilised, collateral, etc.

```bash
curl --request GET \
--url https://api.dhan.co/v2/fundlimit \
--header 'Content-Type: application/json' \
--header 'access-token: JWT'
```

**Request Structure**

_No Body_

**Response Structure**

```json
{
    "dhanClientId":"1000000009",
    "availabelBalance": 98440.0,
    "sodLimit": 113642,
    "collateralAmount": 0.0,
    "receiveableAmount": 0.0,
    "utilizedAmount": 15202.0,
    "blockedPayoutAmount": 0.0,
    "withdrawableBalance": 98310.0
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| availabelBalance | float | Available amount to trade |
| sodLimit | float | Start of the day balance in account |
| collateralAmount | float | Amount received against collateral |
| receiveableAmount | float | Amount available against selling deliveries |
| utilizedAmount | float | Amount utilised in the day |
| blockedPayoutAmount | float | Amount blocked against payout request |
| withdrawableBalance | float | Amount available to withdraw in bank account |

**Note:** For description of enum values, refer [Annexure](#annexure)

---

## Market Quote

This API gives you snapshots of multiple instruments at once. You can fetch LTP, Quote or Market Depth of instruments via API which sends real time data at the time of API request.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /marketfeed/ltp | Get ticker data of instruments |
| POST | /marketfeed/ohlc | Get OHLC data of instruments |
| POST | /marketfeed/quote | Get market depth data of instruments |

**Info:** You can fetch upto 1000 instruments in single API request with rate limit of 1 request per second.

### Ticker Data

Retrieve LTP for list of instruments with single API request

```bash
curl --request POST \
--url https://api.dhan.co/v2/marketfeed/ltp \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--header 'client-id: 1000000001' \
--data '{}'
```

**Header**

| Header | Description |
|--------|-------------|
| access-token _required_ | Access Token generated via Dhan |
| client-id _required_ | User specific identification generated by Dhan |

**Request Structure**

```json
{
"NSE_EQ":[11536],
"NSE_FNO":[49081,49082]
}
```

**Parameters**

| Field | Field Type | Description |
|-------|------------|-------------|
| [Exchange Segment ENUM](#exchange-segment) _required_ | array | Security ID - can be found [here](#instruments) |

**Response Structure**

```json
{
    "data": {
        "NSE_EQ": {
            "11536": {
                "last_price": 4520
            }
        },
        "NSE_FNO": {
            "49081": {
                "last_price": 368.15
            },
            "49082": {
                "last_price": 694.35
            }
        }
    },
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| last_price | float | LTP of the Instrument |

### OHLC Data

Retrieve the Open, High, Low and Close price along with LTP for specified list of instruments.

```bash
curl --request POST \
--url https://api.dhan.co/v2/marketfeed/ohlc \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--header 'client-id: 1000000001' \
--data '{}'
```

**Header**

| Header | Description |
|--------|-------------|
| access-token _required_ | Access Token generated via Dhan |
| client-id _required_ | User specific identification generated by Dhan |

**Request Structure**

```json
{
"NSE_EQ":[11536],
"NSE_FNO":[49081,49082]
}
```

**Parameters**

| Field | Field Type | Description |
|-------|------------|-------------|
| [Exchange Segment ENUM](#exchange-segment) _required_ | array | Security ID - can be found [here](#instruments) |

**Response Structure**

```json
{
    "data": {
        "NSE_EQ": {
            "11536": {
                "last_price": 4525.55,
                "ohlc": {
                    "open": 4521.45,
                    "close": 4507.85,
                    "high": 4530,
                    "low": 4500
                }
            }
        },
        "NSE_FNO": {
            "49081": {
                "last_price": 368.15,
                "ohlc": {
                    "open": 0,
                    "close": 368.15,
                    "high": 0,
                    "low": 0
                }
            },
            "49082": {
                "last_price": 694.35,
                "ohlc": {
                    "open": 0,
                    "close": 694.35,
                    "high": 0,
                    "low": 0
                }
            }
        }
    },
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| last_price | float | LTP of the Instrument |
| ohlc.open | float | Market opening price of the day |
| ohlc.close | float | Market closing price of the day |
| ohlc.high | float | Day High price |
| ohlc.low | float | Day Low price |

### Market Depth Data

Retrieve full details including market depth, OHLC data, Open Interest and Volume along with LTP for specified instruments.

```bash
curl --request POST \
--url https://api.dhan.co/v2/marketfeed/quote \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--header 'client-id: 1000000001' \
--data '{}'
```

**Header**

| Header | Description |
|--------|-------------|
| access-token _required_ | Access Token generated via Dhan |
| client-id _required_ | User specific identification generated by Dhan |

**Request Structure**

```json
{   
    "NSE_FNO":[49081]
}
```

**Response Structure**

```json
{
    "data": {
        "NSE_FNO": {
            "49081": {
                "average_price": 0,
                "buy_quantity": 1825,
                "depth": {
                    "buy": [
                        {
                            "quantity": 1800,
                            "orders": 1,
                            "price": 77
                        },
                        {
                            "quantity": 25,
                            "orders": 1,
                            "price": 50
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        }
                    ],
                    "sell": [
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        },
                        {
                            "quantity": 0,
                            "orders": 0,
                            "price": 0
                        }
                    ]
                },
                "last_price": 368.15,
                "last_quantity": 0,
                "last_trade_time": "01/01/1980 00:00:00",
                "lower_circuit_limit": 48.25,
                "net_change": 0,
                "ohlc": {
                    "open": 0,
                    "close": 368.15,
                    "high": 0,
                    "low": 0
                },
                "oi": 0,
                "oi_day_high": 0,
                "oi_day_low": 0,
                "sell_quantity": 0,
                "upper_circuit_limit": 510.85,
                "volume": 0
            }
        }
    },
    "status": "success"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| average_price | float | Volume weighted average price of the day |
| buy_quantity | int | Total buy order quantity pending at the exchange |
| sell_quantity | int | Total sell order quantity pending at the exchange |
| depth.buy.quantity | int | Number of quantity at this price depth |
| depth.buy.orders | int | Number of open BUY orders at this price depth |
| depth.buy.price | float | Price at which the BUY depth stands |
| depth.sell.quantity | int | Number of quantity at this price depth |
| depth.sell.orders | int | Number of open SELL orders at this price depth |
| depth.sell.price | float | Price at which the SELL depth stands |
| last_price | float | Last traded price |
| last_quantity | int | Last traded quantity |
| last_trade_time | string | Last traded quantity |
| lower_circuit_limit | float | Current lower circuit limit |
| upper_circuit_limit | float | Current upper circuit limit |
| net_change | float | Absolute change in LTP from previous day closing price |
| volume | int | Total traded volume for the day |
| oi | int | Open Interest in the contract (for Derivatives) |
| oi_day_high | int | Highest Open Interest for the day (only for NSE_FNO) |
| oi_day_low | int | Lowest Open Interest for the day (only for NSE_FNO) |
| ohlc.open | float | Market opening price of the day |
| ohlc.close | float | Market closing price of the day |
| ohlc.high | float | Day High price |
| ohlc.low | float | Day Low price |

**Note:** For description of enum values, refer [Annexure](#annexure)

---

## Historical Data

This API gives you historical candle data for the desired scrip across segments & exchange. This data is presented in the form of a candle and gives you timestamp, open, high, low, close & volume.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /charts/historical | Get OHLC for daily timeframe |
| POST | /charts/intraday | Get OHLC for minute timeframe |

### Daily Historical Data

Retrieve OHLC & Volume of daily candle for desired instrument. The data for any scrip is available back upto the date of its inception.

```bash
curl --request POST \
--url https://api.dhan.co/v2/charts/historical \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{}'
```

**Request Structure**

```json
{
    "securityId": "1333",
    "exchangeSegment":"NSE_EQ",
    "instrument": "EQUITY",
    "expiryCode": 0,
    "oi": false,
    "fromDate": "2022-01-08",
    "toDate": "2022-02-08"
}
```

**Parameters**

| Field | Field Type | Description |
|-------|------------|-------------|
| securityId _required_ | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| exchangeSegment _required_ | enum string | Exchange & segment for which data is to be fetched - [here](#exchange-segment) |
| instrument _required_ | enum string | Instrument type of the scrip. Refer [here](#instrument) |
| expiryCode _optional_ | enum integer | Expiry of the instruments in case of derivatives. Refer [here](#instruments) |
| oi _optional_ | boolean | Open Interest data for Futures & Options |
| fromDate _required_ | string | Start date of the desired range |
| toDate _required_ | string | End date of the desired range (non-inclusive) |

**Response Structure**

```json
{
    "open": [3978,3856,3925,3918,3877.85,3992.7,4033.95,4012,3910,3807,3840,3769.5,3731,3646,3749,3770,3827.9,3851,3815.3,3791],
    "high": [3978,3925,3929,3923,3977,4043,4041.7,4012,3920,3851.55,3849.65,3809.4,3733.4,3729.8,3758,3808,3864,3882.5,3824.7,3831.8],
    "low": [3861,3856,3836.55,3857,3860.05,3962.3,3980,3910.5,3811,3771.1,3740.1,3722.2,3625.1,3646,3721.4,3736.4,3800.65,3816.05,3769,3756.15],
    "close": [3879.85,3915.9,3859.9,3897.9,3968.15,4019.15,3990.6,3914.65,3826.55,3833.5,3771.35,3769.9,3649.25,3690.05,3736.25,3800.65,3856.2,3824.6,3814.9,3779],
    "volume": [3937092,1906106,3203744,6684507,3348123,3442604,2389041,3102539,6176776,3112358,3258414,3330501,5718297,3143862,2739393,2105169,1984212,1960538,2307366,1919149],
    "timestamp": [1326220200,1326306600,1326393000,1326479400,1326565800,1326825000,1326911400,1326997800,1327084200,1327170600,1327429800,1327516200,1327689000,1327775400,1328034600,1328121000,1328207400,1328293800,1328380200,1328639400],
    "open_interest": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
}
```

**Parameters**

| Field | Field Type | Description |
|-------|------------|-------------|
| open | float | Open price of the timeframe |
| high | float | High price in the timeframe |
| low | float | Low price in the timeframe |
| close | float | Close price of the timeframe |
| volume | int | Volume traded in the timeframe |
| timestamp | int | Epoch timestamp |

### Intraday Historical Data

Retrieve Open, High, Low, Close, OI & Volume of 1, 5, 15, 25 and 60 min candle for desired instrument for last 5 years. This data available for all exchanges and segments for all active instruments.

```bash
curl --request POST \
--url https://api.dhan.co/v2/charts/intraday \
--header 'Accept: application/json' \
--header 'Content-Type: application/json' \
--header 'access-token: ' \
--data '{}'
```

**Request Structure**

```json
{
"securityId": "1333",
"exchangeSegment": "NSE_EQ",
"instrument": "EQUITY",
"interval": "1",
"oi": false,
"fromDate": "2024-09-11 09:30:00",
"toDate": "2024-09-15 13:00:00"
}
```

**Parameters**

| Field | Field Type | Description |
|-------|------------|-------------|
| securityId _required_ | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| exchangeSegment _required_ | enum string | Exchange & segment for which data is to be fetched - [here](#exchange-segment) |
| instrument _required_ | enum string | Instrument type of the scrip. Refer [here](#instrument) |
| interval _required_ | enum integer | Minute intervals in timeframe: `1`, `5`, `15`, `25`, `60` |
| oi _optional_ | boolean | Open Interest data for Futures & Options |
| fromDate _required_ | string | Start date of the desired range |
| toDate _required_ | string | End date of the desired range |

**Note:** The data size is very large in this scenario and only 90 days of data can be polled at once for any of the above time intervals. It is recommended that you store this data at your end for day-to-day analysis.

**Response Structure**

Similar to Daily Historical Data response with arrays for open, high, low, close, volume, timestamp, and open_interest.

**Parameters**

| Field | Field Type | Description |
|-------|------------|-------------|
| open | float | Open price of the timeframe |
| high | float | High price in the timeframe |
| low | float | Low price in the timeframe |
| close | float | Close price of the timeframe |
| volume | int | Volume traded in the timeframe |
| timestamp | int | Epoch timestamp |

**Note:** For description of enum values, refer [Annexure](#annexure)

---

## Live Market Feed

Real-time Market Data across exchanges and segments can now be availed on your system via WebSocket. WebSocket provides an efficient means to receive live market data. WebSocket keeps a persistent connection open, allowing the server to push real-time data to your systems.

All Dhan platforms work on these same market feed WebSocket connections that deliver lightning fast market data to you. Do note that this is **tick-by-tick event based data** that is sent over the websocket.

> You can establish upto five WebSocket connections per user with 5000 instruments on each connection.

All request messages over WebSocket are in JSON whereas all response messages over WebSocket are in Binary. You will require WebSocket library in any programming language to be able to use Live Market Feed along with Binary converter.

**Using DhanHQ Libraries for WebSockets**

You can use [DhanHQ Python Library](https://github.com/dhan-oss/DhanHQ-py) to quick start with Live Market Feed.

### Establishing Connection

To establish connection with DhanHQ WebSocket for Market Feed, you can to the below endpoint using WebSocket library.

```
wss://api-feed.dhan.co?version=2&token=eyxxxxx&clientId=100xxxxxxx&authType=2
```

**Query Parameters**

| Field | Description |
|-------|-------------|
| version _required_ | `2` for DhanHQ v2 |
| token _required_ | Access Token generated via Dhan |
| clientId _required_ | User specific identification generated by Dhan |
| authType _required_ | `2` by Default |

### Adding Instruments

You can subscribe upto 5000 instruments in a single connection and receive market data packets. For subscribing, this can be done using JSON message which needs to be send over WebSocket connection.

**Note:** You can only send upto 100 instruments in a single JSON message. You can send multiple messages over a single connection to subscribe to all instruments and receive data.

**Request Structure**

```json
{
    "RequestCode" : 15,
    "InstrumentCount" : 2,
    "InstrumentList" : [
        {
            "ExchangeSegment" : "NSE_EQ",
            "SecurityId" : "1333"
        },
        {
            "ExchangeSegment" : "BSE_EQ",
            "SecurityId" : "532540"
        }
    ]
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| RequestCode _required_ | int | Code for subscribing to particular data mode. Refer to [feed request code](#feed-request-code) to subscribe to required data mode |
| InstrumentCount _required_ | int | No. of instruments to subscribe from this request |
| InstrumentList.ExchangeSegment _required_ | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](#exchange-segment) |
| InstrumentList.SecurityId _required_ | string | Exchange standard ID for each scrip. Refer [here](#instruments) |

### Keeping Connection Alive

To keep the WebSocket connection alive and prevent it from closing, the server side uses **Ping-Pong** module. Server side sends ping every 10 seconds to the client server (in this case, your system) to maintain WebSocket status as open.

An automated pong is sent by websocket library. You can use the same as response to the ping.

> In case the client server does not respond for more than 40 seconds, the connection is closed from server side and you will have to reestablish connection.

### Market Data

The market feed data is sent as structured binary packet which is shared at super fast speed.

DhanHQ Live Market Feed is real-time data and there are three modes in which you can receive the data, depending on your use case:

- [Ticker Data](#ticker-packet)
- [Quote Data](#quote-packet)
- [Full Data](#full-packet)

![Subscribing Instruments](https://dhanhq.co/docs/v2/img/WS02.png)

### Binary Response

Binary messages consist of sequences of bytes that represent the data. This contrasts with text messages, which use character encoding (e.g., UTF-8) to represent data in a readable format. Binary messages require parsing to extract the relevant information.

The reason for us to choose binary messages over text or JSON is to have compactness, speed and flexibility on data to be shared at lightning fast speed.

All responses from Dhan Market Feed consists of [Response Header](#response-header) and Payload. Header for every response message remains the same with different [feed response code](#feed-response-code), while the payload can be different.

**Endianness**

Endianness determines the order in which bytes are arranged for multi-byte data (like integers and floats).

**Types:**
- **Little Endian**: Least significant byte first (0x78, 0x56, 0x34, 0x12)
- **Big Endian**: Most significant byte first (0x12, 0x34, 0x56, 0x78)

The data on DhanHQ Websockets are sent in Little Endian. In case your system is Big Endian, you will have to define endianness while reading the websocket.

The response header message is of 8 bytes which will remain same as part of all the response messages. The message structure is given as below.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `1` | [] byte | `1` | Feed Response Code can be referred in [Annexure](#feed-response-code) |
| `2-3` | int16 | `2` | Message Length of the entire payload packet |
| `4` | [] byte | `1` | Exchange Segment can be referred in [Annexure](#exchange-segment) |
| `5-8` | int32 | `4` | Security ID - can be found [here](#instruments) |

### Ticker Packet

This packet consists of Last Traded Price (LTP) and Last Traded Time (LTT) data across segments.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `0-8` | [] array | `8` | [Response Header](#response-header) with code `2` Refer to [enum](#feed-response-code) for values |
| `9-12` | float32 | `4` | Last Traded Price of the subscribed instrument |
| `13-16` | int32 | `4` | Last Trade Time (EPOCH) |

#### Prev Close

Whenever any instrument is subscribed for any data packet, we also send this packet which has Previous Day data to make it easier for day on day comparison.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `0-8` | [] array | `8` | [Response Header](#response-header) with code `6` Refer to [enum](#feed-response-code) for values |
| `9-12` | float32 | `4` | Previous day closing price |
| `13-16` | int32 | `4` | Open Interest - previous day |

### Quote Packet

This data packet is for all instruments across segments and exchanges which consists of complete trade data, along with Last Trade Price (LTP) and other information like update time and quantity.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `0-8` | [] array | `8` | [Response Header](#response-header) with code `4` Refer to [enum](#feed-response-code) for values |
| `9-12` | float32 | `4` | Latest Traded Price of the subscribed instrument |
| `13-14` | int16 | `2` | Last Traded Quantity |
| `15-18` | int32 | `4` | Last Trade Time (LTT) - EPOCH |
| `19-22` | float32 | `4` | Average Trade Price (ATP) |
| `23-26` | int32 | `4` | Volume |
| `27-30` | int32 | `4` | Total Sell Quantity |
| `31-34` | int32 | `4` | Total Buy Quantity |
| `35-38` | float32 | `4` | Day Open Value |
| `39-42` | float32 | `4` | Day Close Value - only sent post market close |
| `43-46` | float32 | `4` | Day High Value |
| `47-50` | float32 | `4` | Day Low Value |

#### OI Data

Whenever you subscribe to Quote Data, you also receive Open Interest (OI) data packets which is important for Derivative Contracts.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `0-8` | [] array | `8` | [Response Header](#response-header) with code `5` Refer to [enum](#feed-response-code) for values |
| `9-12` | int32 | `4` | Open Interest of the contract |

### Full Packet

This data packet is for all instruments across segments and exchanges which consists of complete trade data along with Market Depth and OI data in a single packet.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `0-8` | [] array | `8` | [Response Header](#response-header) with code `8` Refer to [enum](#feed-response-code) for values |
| `9-12` | float32 | `4` | Latest Traded Price of the subscribed instrument |
| `13-14` | int16 | `2` | Last Traded Quantity |
| `15-18` | int32 | `4` | Last Trade Time (LTT) - EPOCH |
| `19-22` | float32 | `4` | Average Trade Price (ATP) |
| `23-26` | int32 | `4` | Volume |
| `27-30` | int32 | `4` | Total Sell Quantity |
| `31-34` | int32 | `4` | Total Buy Quantity |
| `35-38` | int32 | `4` | Open Interest in the contract (for Derivatives) |
| `39-42` | int32 | `4` | Highest Open Interest for the day (only for NSE_FNO) |
| `43-46` | int32 | `4` | Lowest Open Interest for the day (only for NSE_FNO) |
| `47-50` | float32 | `4` | Day Open Value |
| `51-54` | float32 | `4` | Day Close Value - only sent post market close |
| `55-58` | float32 | `4` | Day High Value |
| `59-62` | float32 | `4` | Day Low Value |
| `63-162` | Market Depth Structure | `100` | 5 packets of 20 bytes each for each instrument in below provided structure |

Each of these 5 packets will be received in the following packet structure:

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `1-4` | int32 | `4` | Bid Quantity |
| `5-8` | int32 | `4` | Ask Quantity |
| `9-10` | int16 | `2` | No. of Bid Orders |
| `11-12` | int16 | `2` | No. of Ask Orders |
| `13-16` | float32 | `4` | Bid Price |
| `17-20` | float32 | `4` | Ask Price |

### Feed Disconnect

If you want to disconnect WebSocket, you can send below JSON request message via the connection.

```json
{
    "RequestCode" : 12
}
```

In case of WebSocket disconnection from server side, you will receive disconnection packet, which will have disconnection reason code.

- If more than 5 websockets are established, then the first socket will be disconnected with `805` with every additional connection.

| Bytes | Type | Size | Description |
|-------|------|------|-------------|
| `0-8` | [] array | `8` | [Response Header](#response-header) with code `50` Refer to [enum](#feed-response-code) for values |
| `9-10` | int16 | `2` | Disconnection message code - [here](#data-api-error) |

You can find detailed Disconnection message code description [here](#data-api-error).

---

## Statements

This set of APIs retreives all your trade and ledger details to help you summarise and analyse your trades.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /ledger | Retrieve Trading Account debit and credit details |
| GET | /trades/ | Retrieve historical trade data |

### Ledger Report

Users can retrieve Trading Account Ledger Report with all Credit and Debit transaction details for a particular time interval. For this, you need to pass start date and end date as query parameters to define time interval of Ledger Report.

```bash
curl --request GET \
--url 'https://api.dhan.co/v2/ledger?from-date={YYYY-MM-DD}&to-date={YYYY-MM-DD}' \
--header 'Accept: application/json' \
--header 'access-token: {JWT}'
```

**Query Parameters**

| Field | Description |
|-------|-------------|
| from-date _required_ | Date from which Ledger Report is required in format `YYYY-MM-DD` |
| to-date _required_ | Date upto which Ledger Report is required in format `YYYY-MM-DD` |

**Request Structure**

_No Body_

**Response Structure**

```json
{
    "dhanClientId": "1000000001",
    "narration": "FUNDS WITHDRAWAL",
    "voucherdate": "Jun 22, 2022",
    "exchange": "NSE-CAPITAL",
    "voucherdesc": "PAYBNK",
    "vouchernumber": "202200036701",
    "debit": "20000.00",
    "credit": "0.00",
    "runbal": "957.29"
}
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| narration | string | Description of the ledger transaction |
| voucherdate | string | Transaction Date |
| exchange | string | Exchange information for the transaction |
| voucherdesc | string | Nature of transaction |
| vouchernumber | string | System generated transaction number |
| debit | string | Debit amount (only when credit returns 0) |
| credit | string | Credit amount (only when debit returns 0) |
| runbal | string | Running Balance post transaction |

### Trade History

Users can retrieve their detailed trade history for all orders for a particular time frame. User needs to add header parameters along with page number as the response is paginated.

```bash
curl --request GET \
--url https://api.dhan.co/v2/trades/{from-date}/{to-date}/{page} \
--header 'Accept: application/json' \
--header 'access-token: {JWT}'
```

**Path Parameters**

| Field | Description |
|-------|-------------|
| from-date _required_ | Date from which Trade History is required in format `YYYY-MM-DD` |
| to-date _required_ | Date upto which Trade History is required in format `YYYY-MM-DD` |
| page _required_ | Page number of which data is being fetched. Pass `0` as default. |

**Request Structure**

_No Body_

**Response Structure**

```json
[
    {
    "dhanClientId": "1000000001",
    "orderId": "212212307731",
    "exchangeOrderId": "76036896",
    "exchangeTradeId": "407958",
    "transactionType": "BUY",
    "exchangeSegment": "NSE_EQ",
    "productType": "CNC",
    "orderType": "MARKET",
    "tradingSymbol": null,
    "customSymbol": "Tata Motors",
    "securityId": "3456",
    "tradedQuantity": 1,
    "tradedPrice": 390.9,
    "isin": "INE155A01022",
    "instrument": "EQUITY",
    "sebiTax": 0.0004,
    "stt": 0,
    "brokerageCharges": 0,
    "serviceTax": 0.0025,
    "exchangeTransactionCharges": 0.0135,
    "stampDuty": 0,
    "createTime": "NA",
    "updateTime": "NA",
    "exchangeTime": "2022-12-30 10:00:46",
    "drvExpiryDate": "NA",
    "drvOptionType": "NA",
    "drvStrikePrice": 0
    } 
]
```

**Parameters**

| Field | Type | Description |
|-------|------|-------------|
| dhanClientId | string | User specific identification generated by Dhan |
| orderId | string | Order specific identification generated by Dhan |
| exchangeOrderId | string | Order specific identification generated by exchange |
| exchangeTradeId | string | Trade specific identification generated by exchange |
| transactionType | enum string | The trading side of transaction: `BUY` `SELL` |
| exchangeSegment | enum string | Exchange Segment of instrument to be subscribed as found in [Annexure](#exchange-segment) |
| productType | enum string | Product type of trade: `CNC` `INTRADAY` `MARGIN` `MTF` `CO` `BO` |
| orderType | enum string | Order Type: `LIMIT` `MARKET` `STOP_LOSS` `STOP_LOSS_MARKET` |
| tradingSymbol | string | Symbol in which order was placed - Refer [here](#instruments) |
| customSymbol | string | Trading Symbol as per Dhan |
| securityId | string | Exchange standard ID for each scrip. Refer [here](#instruments) |
| tradedQuantity | int | Number of shares executed |
| tradedPrice | float | Price at which trade is executed |
| isin | string | Universal standard ID for each scrip |
| instrument | string | Type of Instrument: `EQUITY` `DERIVATIVES` |
| sebiTax | string | SEBI Turnover Charges |
| stt | string | Securities Transactions Tax |
| brokerageCharges | string | Brokerage charges by Dhan, refer pricing [here](https://dhan.co/pricing/) |
| serviceTax | string | Applicable Service Tax |
| exchangeTransactionCharges | string | Exchange Transaction Charge |
| stampDuty | string | Stamp Duty Charges |
| createTime | string | Time at which the order is created |
| updateTime | string | Time at which the last activity happened |
| exchangeTime | string | Time at which order reached at exchange |
| drvExpiryDate | int | For F&O, expiry date of contract |
| drvOptionType | enum string | Type of Option: `CALL` `PUT` |
| drvStrikePrice | float | For Options, Strike Price |

**Note:** For description of enum values, refer [Annexure](#annexure)

---

## Instruments

You can fetch instrument list for all instruments which can be traded via Dhan by using below URL:

**Compact:**

```
https://images.dhan.co/api-data/api-scrip-master.csv
```

**Detailed:**

```
https://images.dhan.co/api-data/api-scrip-master-detailed.csv
```

This fetches list of instruments as CSV with Security ID and other important details which will help you build with DhanHQ APIs.

### Segmentwise List

You can fetch detailed instrument list for all instruments in a particular exchange and segment by passing the same in parameters as below:

```bash
curl --location 'https://api.dhan.co/v2/instrument/{exchangeSegment}'
```

> This helps to fetch instrument list of only one particular `exchangeSegment` at a time. The mapping of the same can be found [here](#exchange-segment).

### Column Description

| Detailed tag | Compact tag | Description |
|--------------|-------------|-------------|
| `EXCH_ID` | `SEM_EXM_EXCH_ID` | Exchange: `NSE` `BSE` `MCX` |
| `SEGMENT` | `SEM_SEGMENT` | Segment: `C` - Currency, `D` - Derivatives, `E` - Equity, `M` - Commodity |
| `ISIN` | - | International Securities Identification Number(ISIN) - 12-digit alphanumeric code unique for instruments |
| `INSTRUMENT` | `SEM_INSTRUMENT_NAME` | Instrument defined by Exchange - defined [here](#instrument) |
| _removed_ | `SEM_EXPIRY_CODE` | Expiry Code (applicable in case of Futures Contract) - defined [here](#expiry-code) |
| `UNDERLYING_SECURITY_ID` | - | Security ID of underlying instrument (applicable in case of derivative contracts) |
| `UNDERLYING_SYMBOL` | - | Symbol of underlying instrument (applicable in case of derivative contracts) |
| `SYMBOL_NAME` | `SM_SYMBOL_NAME` | Symbol name of instrument |
| _removed_ | `SEM_TRADING_SYMBOL` | Exchange trading symbol of instrument |
| `DISPLAY_NAME` | `SEM_CUSTOM_SYMBOL` | Dhan display symbol name of instrument |
| `INSTRUMENT_TYPE` | `SEM_EXCH_INSTRUMENT_TYPE` | In addition to `INSTRUMENT` column, instrument type is defined by exchange adding more details about instrument |
| `SERIES` | `SEM_SERIES` | Exchange defined series for instrument |
| `LOT_SIZE` | `SEM_LOT_UNITS` | Lot Size in multiples of which instrument is traded |
| `SM_EXPIRY_DATE` | `SEM_EXPIRY_DATE` | Expiry date of instrument (applicable in case of derivative contracts) |
| `STRIKE_PRICE` | `SEM_STRIKE_PRICE` | Strike Price of Options Contract |
| `OPTION_TYPE` | `SEM_OPTION_TYPE` | Type of Options Contract: `CE` - Call, `PE` - Put |
| `TICK_SIZE` | `SEM_TICK_SIZE` | Minimum decimal point at which an instrument can be priced |
| `EXPIRY_FLAG` | `SEM_EXPIRY_FLAG` | Type of Expiry (applicable in case of option contracts): `M` - Monthly Expiry, `W` - Weekly Expiry |
| `BRACKET_FLAG` | - | Bracket order status: `N` - Not available, `Y` - Allowed |
| `COVER_FLAG` | - | Cover order status: `N` - Not available, `Y` - Allowed |
| `ASM_GSM_FLAG` | - | Flag for instrument is ASM or GSM: `N` - Not in ASM/GSM, `R` - Removed from block, `Y` - ASM/GSM |
| `ASM_GSM_CATEGORY` | - | Category of instrument in ASM or GSM: `NA` in case of no surveillance |
| `BUY_SELL_INDICATOR` | - | Indicator to show if Buy and Sell is allowed in instrument: `A` if both Buy/Sell is allowed |
| `BUY_CO_MIN_MARGIN_PER` | - | Buy cover order minimum margin requirement (in percentage) |
| `SELL_CO_MIN_MARGIN_PER` | - | Sell cover order minimum margin requirement (in percentage) |
| `BUY_CO_SL_RANGE_MAX_PERC` | - | Buy cover order maximum range for stop loss leg (in percentage) |
| `SELL_CO_SL_RANGE_MAX_PERC` | - | Sell cover order maximum range for stop loss leg (in percentage) |
| `BUY_CO_SL_RANGE_MIN_PERC` | - | Buy cover order minimum range for stop loss leg (in percentage) |
| `SELL_CO_SL_RANGE_MIN_PERC` | - | Sell cover order minimum range for stop loss leg (in percentage) |
| `BUY_BO_MIN_MARGIN_PER` | - | Buy bracket order minimum margin requirement (in percentage) |
| `SELL_BO_MIN_MARGIN_PER` | - | Sell bracket order minimum margin requirement (in percentage) |
| `BUY_BO_SL_RANGE_MAX_PERC` | - | Buy bracket order maximum range for stop loss leg (in percentage) |
| `SELL_BO_SL_RANGE_MAX_PERC` | - | Sell bracket order maximum range for stop loss leg (in percentage) |
| `BUY_BO_SL_RANGE_MIN_PERC` | - | Buy bracket order minimum range for stop loss leg (in percentage) |
| `SELL_BO_SL_MIN_RANGE` | - | Sell bracket order minimum range for stop loss leg (in percentage) |
| `BUY_BO_PROFIT_RANGE_MAX_PERC` | - | Buy bracket order maximum range for target leg (in percentage) |
| `SELL_BO_PROFIT_RANGE_MAX_PERC` | - | Sell bracket order maximum range for target leg (in percentage) |
| `BUY_BO_PROFIT_RANGE_MIN_PERC` | - | Buy bracket order minimum range for target leg (in percentage) |
| `SELL_BO_PROFIT_RANGE_MIN_PERC` | - | Sell bracket order minimum range for target leg (in percentage) |
| `MTF_LEVERAGE` | - | MTF Leverage available (in x multiple) for eligible `EQUITY` instruments |

---

## Annexure

### Exchange Segment

| Attribute | Exchange | Segment | enum |
|-----------|----------|---------|------|
| IDX_I | Index | Index Value | `0` |
| NSE_EQ | NSE | Equity Cash | `1` |
| NSE_FNO | NSE | Futures & Options | `2` |
| NSE_CURRENCY | NSE | Currency | `3` |
| BSE_EQ | BSE | Equity Cash | `4` |
| MCX_COMM | MCX | Commodity | `5` |
| BSE_CURRENCY | BSE | Currency | `7` |
| BSE_FNO | BSE | Futures & Options | `8` |

### Product Type

CO & BO product types will be valid only for Intraday.

| Attribute | Detail |
|-----------|--------|
| CNC | Cash & Carry for equity deliveries |
| INTRADAY | Intraday for Equity, Futures & Options |
| MARGIN | Carry Forward in Futures & Options |
| CO | Cover Order |
| BO | Bracket Order |

### Order Status

| Attribute | Detail |
|-----------|--------|
| TRANSIT | Did not reach the exchange server |
| PENDING | Awaiting execution |
| CLOSED | Used for Super Order, once both the entry and exit orders are placed |
| TRIGGERED | Used for Super Order, if Target or Stop Loss leg is triggered |
| REJECTED | Rejected by broker/exchange |
| CANCELLED | Cancelled by user |
| PART_TRADED | Partial Quantity traded successfully |
| TRADED | Executed successfully |

### After Market Order time

| Attribute | Detail |
|-----------|--------|
| PRE_OPEN | AMO pumped at pre-market session |
| OPEN | AMO pumped at market open |
| OPEN_30 | AMO pumped 30 minutes after market open |
| OPEN_60 | AMO pumped 60 minutes after market open |

### Expiry Code

| Attribute | Detail |
|-----------|--------|
| 0 | Current Expiry/Near Expiry |
| 1 | Next Expiry |
| 2 | Far Expiry |

### Instrument

| Attribute | Detail |
|-----------|--------|
| INDEX | Index |
| FUTIDX | Futures of Index |
| OPTIDX | Options of Index |
| EQUITY | Equity |
| FUTSTK | Futures of Stock |
| OPTSTK | Options of Stock |
| FUTCOM | Futures of Commodity |
| OPTFUT | Options of Commodity Futures |
| FUTCUR | Futures of Currency |
| OPTCUR | Options of Currency |

### Feed Request Code

| Attribute | Detail |
|-----------|--------|
| `11` | Connect Feed |
| `12` | Disconnect Feed |
| `15` | Subscribe - Ticker Packet |
| `16` | Unsubscribe - Ticker Packet |
| `17` | Subscribe - Quote Packet |
| `18` | Unsubscribe - Quote Packet |
| `21` | Subscribe - Full Packet |
| `22` | Unsubscribe - Full Packet |
| `23` | Subscribe - 20 Level Market Depth |
| `24` | Unsubscribe - 20 Level Market Depth |

### Feed Response Code

| Attribute | Detail |
|-----------|--------|
| `1` | Index Packet |
| `2` | Ticker Packet |
| `4` | Quote Packet |
| `5` | OI Packet |
| `6` | Prev Close Packet |
| `7` | Market Status Packet |
| `8` | Full Packet |
| `50` | Feed Disconnect |

### Trading API Error

| Type | Code | Message |
|------|------|---------|
| Invalid Authentication | `DH-901` | Client ID or user generated access token is invalid or expired. |
| Invalid Access | `DH-902` | User has not subscribed to Data APIs or does not have access to Trading APIs. Kindly subscribe to Data APIs to be able to fetch Data. |
| User Account | `DH-903` | Errors related to User's Account. Check if the required segments are activated or other requirements are met. |
| Rate Limit | `DH-904` | Too many requests on server from single user breaching rate limits. Try throttling API calls. |
| Input Exception | `DH-905` | Missing required fields, bad values for parameters etc. |
| Order Error | `DH-906` | Incorrect request for order and cannot be processed. |
| Data Error | `DH-907` | System is unable to fetch data due to incorrect parameters or no data present. |
| Internal Server Error | `DH-908` | Server was not able to process API request. This will only occur rarely. |
| Network Error | `DH-909` | Network error where the API was unable to communicate with the backend system. |
| Others | `DH-910` | Error originating from other reasons. |

### Data API Error

| Code | Description |
|------|-------------|
| `800` | Internal Server Error |
| `804` | Requested number of instruments exceeds limit |
| `805` | Too many requests or connections. Further requests may result in the user being blocked. |
| `806` | Data APIs not subscribed |
| `807` | Access token is expired |
| `808` | Authentication Failed - Client ID or Access Token invalid |
| `809` | Access token is invalid |
| `810` | Client ID is invalid |
| `811` | Invalid Expiry Date |
| `812` | Invalid Date Format |
| `813` | Invalid SecurityId |
| `814` | Invalid Request |

---

**Source:** [DhanHQ API v2.0 Documentation](https://dhanhq.co/docs/v2/)