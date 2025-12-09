Here's the documentation from both URLs in markdown format:

---

# DhanHQ Documentation - Getting Started

## Getting Started

![DhanHQ Banner](https://sspark.genspark.ai/cfimages?u1=3yTAxFxycxG6Lnmuhos1zDkh0L5OdrC5DgzBW2APOubKYeWDBs%2BeMglbMOHzBx7c9yhZ%2FXYwiQ%3D%3D&u2=ON6nu%2B077SWfRgbB&width=1024)

DhanHQ API is a state-of-the-art platform for you to build trading and investment services & strategies.

It is a set of REST-like APIs that provide integration with our trading platform. Execute & modify orders in real time, manage portfolio, access live market data and more, with lightning fast API collection.

We offer resource-based URLs that accept JSON or form-encoded requests. The response is returned as JSON-encoded responses by using Standard HTTP response codes, verbs, and authentication.

### Developer Resources

- **Developer Kit**
- **DhanHQ Python Client**

## Structure

### REST API

All GET and DELETE request parameters go as query parameters, and POST and PUT parameters as form-encoded. User has to input an access token in the header for every request.

```bash
curl --request POST \
--url https://api.dhan.co/v2/ \
--header 'Content-Type: application/json' \
--header 'access-token: JWT' \
--data '{Request JSON}'
```

### Python Client

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

You can find detailed error code and message under [Annexure](https://dhanhq.co/docs/v2/annexure/#trading-api-error).

## Rate Limit

| Rate Limit | Order APIs | Data APIs | Quote APIs | Non Trading APIs |
| --- | --- | --- | --- | --- |
| per second | 25 | 5 | 1 | 20 |
| per minute | 250 | - | Unlimited | Unlimited |
| per hour | 1000 | - | Unlimited | Unlimited |
| per day | 7000 | 100000 | Unlimited | Unlimited |

Order Modifications are capped at 25 modifications/order

---

# Authentication

DhanHQ APIs require authentication based on an access token which needs to be passed with every request. There are various different methods to generate this access token depending on user type and the purpose of usage.

There are two categories in which users of DhanHQ APIs are divided:

- **Individual** - Users who have Dhan account and are coders, traders, geeks who want to build their own algorithm or trading system on top of DhanHQ APIs
- **Partners** - Platforms who want to build on top of DhanHQ APIs and serve it to their users. This can be algo platforms, fintechs, banks, PMS, and others.

## Eligibility

All Dhan users get access to Trading APIs for free. This means you can place and manage orders, positions, funds and all other transactions without paying any extra charges. For Data APIs, there are additional charges which are mentioned on the platform.

If you are a partner who wants to get integrated and build on top of DhanHQ APIs, you can reach out to us by filling form on the DhanHQ website [here](https://dhanhq.co/trading-apis). We are looking forward to build the ecosystem around DhanHQ APIs.

## Getting Started

### For Individual Traders

As an individual trader, there are two methods using which a user can generate an access token:

- Directly generate access token from Dhan Web
- Use API key based authentication method

#### Access Token

Individual traders can directly get their Access Token from [web.dhan.co](https://web.dhan.co/). All Dhan users are eligible to get free access to Trading APIs. Here's how to get your Access Token:

- Login to [web.dhan.co](https://web.dhan.co/)
- Click on My Profile and navigate to **'Access DhanHQ APIs'**
- Generate "Access Token" for a validity of 24 hours from there.
- User have an option to enter Postback URL while generating the access token, to get order updates as [Postback](https://dhanhq.co/postback/).

##### Refresh Access Token

You can refresh your token for 24 hours with this endpoint:

```bash
curl --location 'https://api.dhan.co/v2/RenewToken' \
--header 'access-token: {JWT Token}' \
--header 'dhanClientId: {Client ID}'
```

This expires your current token and provides you with a new token with another 24 hours of validity. You can use this only for tokens generated from Dhan Web.

#### API key & secret

Individuals can login with an OAuth based flow as well. All dhan users can generate individual user specific API key and secret. To generate API key and secret, a user needs to follow the below steps:

- Login to [web.dhan.co](https://web.dhan.co/)
- Click on My Profile and navigate to **'Access DhanHQ APIs'**
- Toggle to **'API key'** and enter your app name
- Enter **App name**, **Redirect URL** (to be used at the end of Step 2 provided below) and **Postback URL** (which is option to get updates on [Postback](https://dhanhq.co/postback/)).

> **Note:** API Key & Secret are valid for 12 months from the date of generation

After getting the API key and secret, user needs to follow below three steps, in order to generate access token, which can be used for all other API authentication.

##### STEP 1: Generate Consent

This API is provided to generate consent to initiate a login session. On this step, the App ID and secret is validated and a new session is created for the user to enter credentials.

```bash
curl --location --request POST 'https://auth.dhan.co/app/generate-consent?client_id={dhanClientId}' \
--header 'app_id: {API key}' \
--header 'app_secret: {API secret}'
```

The response of this flow will have `consentAppId`. This `consentAppId` will be required for the next step of browser based flow.

> **Note:** User can generate upto 25 `consentAppId` in a day. Each consent app ID stay active until tokenId is generated for them. However, at any given point of time, only one token will be generated.

**Header**

| Field | Description |
| --- | --- |
| app_id (_required_) | API Key generated from Dhan |
| app_secret (_required_) | API Secret generated from Dhan |

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
| --- | --- |
| consentAppId | Temporary session ID, to be used in step 2 |
| consentAppStatus | Status of the API request |

##### STEP 2: Browser based login

This endpoint needs to be opened directly on a browser. On this step, the user needs to enter their Dhan credentials, validate with 2FA like OTP/pin/password. If the login is successful, the user is redirected to the URL provided while generating the API key. Along with the redirect, we also send `tokenId` which needs to be used in step 3.

> **Note:** This will end up with a 302 redirect on the browser. You can consume the `tokenId` from the path parameter directly.

**Request URL**

```
https://auth.dhan.co/login/consentApp-login?consentAppId={consentAppId}
```

**Path Parameter**

| Field | Description |
| --- | --- |
| consentAppId (_required_) | Temporary session ID created in Generate Consent (I) stage |

**Response Structure**

```
{redirect_URL}/?tokenId={Token ID for user}
```

**Parameters**

| Field | Description |
| --- | --- |
| tokenId | Token ID to be used to generate Access Token |

##### STEP 3: Consume Consent

This API is to generate access token by validating API key & secret and using `tokenId` generated in the above step. This results in the `access token` which needs to be used in all other API endpoints.

```bash
curl --location 'https://auth.dhan.co/app/consumeApp-consent?tokenId={Token ID}' \
--header 'app_id: {API Key}' \
--header 'app_secret: {API Secret}'
```

**Path Parameter**

| Field | Description |
| --- | --- |
| tokenId (_required_) | User specific token ID, obtained in stage II |

**Header**

| Field | Description |
| --- | --- |
| app_id (_required_) | API Key generated from Dhan |
| app_secret (_required_) | API Secret generated from Dhan |

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
| --- | --- |
| dhanClientId | User specific identification generated by Dhan |
| dhanClientName | Name of the User |
| dhanClientUcc | Unique Client Code (UCC) |
| givenPowerOfAttorney | Whether the user has activated DDPI (true/false) |
| accessToken | JWT access token to be used for API authentication |
| expiryTime | ISO timestamp when the access token expires as per IST |

### For Partners

Once partner receives `partner_id` & `partner_secret`, they can use this authentication mechanism for their users.

This login method is a three step based, which is outlined below. This is for all different types of platforms, wherein the user can login to their Dhan account right from the third party platform itself.

##### STEP 1: Generate Consent

This API is to generate consent to initiate a login session for a user. This is to validate the partner and allow them to start the authentication process.

```bash
curl --location 'https://auth.dhan.co/partner/generate-consent' \
--header 'partner_id: {Partner ID}' \
--header 'partner_secret: {Partner Secret}'
```

The response of this flow will have `consentId`. This `consentId` can be used for the next browser based flow.

**Header**

| Field | Description |
| --- | --- |
| partner_id (_required_) | Partner ID provided by Dhan |
| partner_secret (_required_) | Partner Secret provided by Dhan |

**Response Structure**

```json
{
    "consentId": "ab5aaab6-38cb-41fc-a074-c816e2f9a3e0",
    "consentStatus": "GENERATED"
}
```

**Parameters**

| Field | Description |
| --- | --- |
| consentId | Temporary session ID on partner level, to be used in step 2 |

##### STEP 2: Dhan login on browser for user

This endpoint needs to be opened directly on a tab for browser based applications or on the webview for mobile apps. On this step, the end user needs to enter their Dhan credentials, validate with 2FA like OTP/pin/password. If the login is successful, the user is redirected to the URL provided to us. Along with the redirect, we also send `tokenId` which needs to be used in step 3.

> **Note:** This will end up with a 302 redirect on the browser. You can consume the `tokenId` from the path parameter directly.

**Request URL**

```
https://auth.dhan.co/consent-login?consentId={consentId}
```

**Path Parameter**

| Field | Description |
| --- | --- |
| consentId (_required_) | Temporary session ID created in Generate Consent (I) stage |

**Response Structure**

```
{redirect_URL}/?tokenId={Token ID for user}
```

**Parameters**

| Field | Description |
| --- | --- |
| tokenId | Token ID to be used to generate Access Token |

##### STEP 3: Consume Consent

This API is to generate access token by validating partner credentials and using `tokenId` generated in the above step.

```bash
curl --location 'https://auth.dhan.co/partner/consume-consent?tokenId={Token ID}' \
--header 'partner_id: {Partner ID}' \
--header 'partner_secret: {Partner Secret}'
```

**Path Parameter**

| Field | Description |
| --- | --- |
| tokenId (_required_) | User specific token ID, obtained in stage II |

**Header**

| Field | Description |
| --- | --- |
| partner_id (_required_) | Partner ID provided by Dhan |
| partner_secret (_required_) | Partner Secret provided by Dhan |

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
| --- | --- |
| dhanClientId | User specific identification generated by Dhan |
| dhanClientName | Name of the User |
| dhanClientUcc | Unique Client Code (UCC) |
| givenPowerOfAttorney | Whether the user has activated DDPI (true/false) |
| accessToken | JWT access token to be used for API authentication |
| expiryTime | ISO timestamp when the access token expires as per IST |

## Setup Static IP

Static IP whitelisting is mandatory as per the new SEBI and exchange guidelines. In line with this, you can use the below APIs to set Static IP for your account. Alternatively, you can also use Dhan Web ([web.dhan.co](https://web.dhan.co/)) to setup your Static IP.

You can set up a primary and a secondary IP for your account. Do note that each individual needs to have a unique static IP. Once an IP is whitelisted, it cannot be edited for the next 7 days or as recommended by the exchange. Do note that Static IP is only required while using Order Placement APIs including Orders, Super Order, Forever Order. While fetching order details or trade details, no such IP whitelisting is required.

Below set of APIs can be used to manage Static IP for your account.

> **Info:** A static IP is a fixed, permanent internet address for your device or server. Unlike the default IP you get on home Wi-Fi (which your ISP changes automatically from time to time), a static IP never changes. To use one, you need to request and purchase it separately from your Internet Service Provider (ISP).

### Set IP

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
| --- | --- | --- |
| dhanClientId (_required_) | string | User specific identification generated by Dhan |
| ip (_required_) | string | Static IP address in IPv4 or IPv6 format |
| ipFlag (_required_) | string (enum) | Flag to set the IP as primary or secondary: `PRIMARY` / `SECONDARY` |

**Response Structure**

```json
{
"message": "IP saved successfully",
"status": "SUCCESS"
}
```

**Parameters**

| Field | Description |
| --- | --- |
| message | API response confirmation |
| status | Status of the request |

### Modify IP

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
| --- | --- | --- |
| dhanClientId (_required_) | string | User specific identification generated by Dhan |
| ip (_required_) | string | Static IP address in IPv4 or IPv6 format |
| ipFlag (_required_) | string (enum) | Flag to set the IP as primary or secondary: `PRIMARY` / `SECONDARY` |

**Response Structure**

```json
{
"message": "IP saved successfully",
"status": "SUCCESS"
}
```

**Parameters**

| Field | Description |
| --- | --- |
| message | API response confirmation |
| status | Status of the request |

### Get IP

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
| --- | --- | --- |
| modifyDateSecondary | string | Date from which the secondary IP can be modified (YYYY-MM-DD) |
| secondaryIP | string | Currently set secondary static IP (IPv4 or IPv6) |
| modifyDatePrimary | string | Date from which the primary IP can be modified (YYYY-MM-DD) |
| primaryIP | string | Currently set primary static IP (IPv4 or IPv6) |

## Setup TOTP

As an API user, you can setup TOTP to simplify authentication for API-only flows, as an alternative to enter OTP received on email or mobile number.

### What is TOTP?

Time-based One-Time Password (TOTP) is a 6-digit code generated from a shared secret and current time (RFC 6238). Once you enable TOTP for your account, you'll receive a secret (via QR/code) that your server can use to generate a fresh code every 30 seconds.

### How to set up TOTP

1. Go to Dhan Web > DhanHQ Trading APIs section
2. Select Setup TOTP
3. Confirm with OTP on mobile/email
4. Scan the QR via an Authenticator app or enter the code shown into the Authenticator
5. Confirm by entering the first TOTP

Once this is is setup, you will by default see TOTP as an option while logging into any partner platforms or inside the API key based authentication mode.

## User Profile

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
| --- | --- | --- |
| dhanClientId | string | User specific identification generated by Dhan |
| tokenValidity | string | Validity date and time for Token |
| activeSegment | string | All active segments in user accounts |
| ddpi | string | DDPI status of the user: `Active` / `Deactive` |
| mtf | string | MTF consent status of the user: `Active` / `Deactive` |
| dataPlan | string | Data API subscription status: `Active` / `Deactive` |
| dataValidity | string | Validity date and time for Data API Subscription |

---

This markdown documentation covers the complete content from both URLs as it appears on the DhanHQ documentation site.