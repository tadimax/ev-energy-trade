import time
import shutil
from web3 import Web3
from eth_account import Account
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
import solcx
from solcx import compile_source

# --- Solidity compiler setup (Fix A) ---
TARGET_SOLC = "0.8.19"
installed = list(map(str, solcx.get_installed_solc_versions()))
if TARGET_SOLC not in installed:
    print(f"Installing solc {TARGET_SOLC} via solcx...")
    solcx.install_solc(TARGET_SOLC)
solcx.set_solc_version(TARGET_SOLC)

print("Active solc (via solcx):", solcx.get_solc_version())
print("Global solc on PATH:", shutil.which("solc") or "not found")
print("Global solcjs on PATH:", shutil.which("solcjs") or "not found")
# --- end setup ---

# Connect to Ganache
ganache_url = "http://127.0.0.1:7545"
web3 = Web3(Web3.HTTPProvider(ganache_url))

if web3.is_connected():
    print("✅ Connected to Ethereum network")
else:
    raise Exception("❌ Failed to connect to Ethereum")

# === Deploy contract function ===
def deploy_contract(price_wei, song_hash):
    with open("contracts/SongPurchase.sol", "r") as f:
        source = f.read()

    # Compile for an older EVM to avoid invalid opcode on Ganache
    compiled_sol = compile_source(
        source,
        output_values=["abi", "bin"],
        evm_version="berlin",     # or "istanbul"
        optimize=True,
        optimize_runs=200,
    )
    contract_id, contract_interface = next(iter(compiled_sol.items()))

    song_contract = web3.eth.contract(
        abi=contract_interface["abi"],
        bytecode=contract_interface["bin"],
    )

    tx_hash = song_contract.constructor(price_wei, song_hash).transact({
        "from": web3.eth.accounts[0],
        "gas": 3_000_000,
        "gasPrice": web3.to_wei("50", "gwei"),
    })
    print(f"⏳ Deploy tx sent: {tx_hash.hex()}")

    tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"✅ Contract deployed at: {tx_receipt.contractAddress}")

    return web3.eth.contract(address=tx_receipt.contractAddress, abi=contract_interface["abi"])

# === RSA Key Generation ===
def generate_rsa_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key

def encrypt_message(public_key, message):
    return public_key.encrypt(
        message,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )

def decrypt_message(private_key, ciphertext):
    return private_key.decrypt(
        ciphertext,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )

# === Authentication ===
def authenticate_user(address):
    authorized_addresses = [web3.eth.accounts[0]]
    if address not in authorized_addresses:
        raise Exception("Unauthorized access")
    else:
        print("✅ Address is authenticated")

# === MAIN FLOW ===
try:
    print("\n🔐 Generating RSA key pair...")
    private_key, public_key = generate_rsa_keys()

    print("\n🔒 Authenticating user...")
    user_address = web3.eth.accounts[0]
    authenticate_user(user_address)

    print("\n🚀 Deploying a new contract for the song...")
    price = web3.to_wei(0.1, "ether")
    song_hash = f"QmExampleHash_{int(time.time())}"
    contract = deploy_contract(price, song_hash)

    print("\n🎵 Buying the song...")
    tx_hash = contract.functions.buySong().transact({
        "from": user_address,               # unlocked Ganache account
        "value": price,
        "gas": 300_000,
        "gasPrice": web3.to_wei("50", "gwei"),
    })
    print(f"⏳ Transaction sent: {tx_hash.hex()}")
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print("✅ Transaction mined! Receipt:")
    print(receipt)

    print("\n🔐 Encrypting transaction hash...")
    access_key = tx_hash.hex().encode()
    encrypted_key = encrypt_message(public_key, access_key)
    print(f"Encrypted access key: {encrypted_key[:32]}...")

    print("\n🔓 Decrypting transaction hash...")
    decrypted_key = decrypt_message(private_key, encrypted_key)
    print(f"Decrypted access key: {decrypted_key.decode()}")

except Exception as e:
    print(f"❌ Error: {e}")
