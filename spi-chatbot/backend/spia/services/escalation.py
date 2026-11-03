"""Missing-knowledge signals, team routing and private WhatsApp contacts."""
import os
import re
import unicodedata
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from spia.services import chat_history as h

MARKER='[[SPIA_NO_KNOWLEDGE]]'
LEGACY_EN='I could not find this in the permitted reference material.'
LEGACY_UR='مجھے اجازت یافتہ حوالہ جاتی مواد میں اس سوال کا جواب نہیں ملا۔'
TEAMS=('support','implementation')
PROMPT=(
    ' If the permitted references and visible screenshot evidence cannot answer the request, '
    'begin the reply with [[SPIA_NO_KNOWLEDGE]] and briefly explain the missing knowledge. '
    'Use that marker only for missing knowledge, including a partial answer that needs team help. '
    'Do not use it for a clarification question or a fully supported screenshot validation action. '
    'Never claim a WhatsApp message was sent or invent contact details.'
)

def normal(text):
    return ' '.join(unicodedata.normalize('NFKC',text).strip().split()).casefold()

def pack_reply(reply,expert):
    text=reply.strip()
    marked=text.startswith(MARKER)
    if marked:
        text=text[len(MARKER):].lstrip()
    missing=marked or normal(text) in (normal(LEGACY_EN),normal(LEGACY_UR))
    return text,{
        'eligible':missing,
        'reason':'missing_knowledge' if missing else None,
        'department':expert if expert in TEAMS else None,
    }

def eligible(reply,metadata=None):
    stored=(
        isinstance(metadata,dict)
        and metadata.get('eligible') is True
        and metadata.get('reason')=='missing_knowledge'
    )
    return bool(stored) or pack_reply(reply,'')[1]['eligible']

def department(question,expert):
    q=normal(question)
    if re.search(
        r'\b(install(?:ation|ing)?|deploy(?:ment)?|migrat(?:e|ion)|initial setup)\b|تنصیب|انسٹال|ڈیپلائے|مائیگریشن',
        q
    ):
        return 'implementation','installation_or_migration'
    if re.search(
        r'\b(error|crash(?:ing)?|fail(?:ed|ure)?|bug|stuck|not working|not running|not showing|unable)\b|خرابی|مسئلہ|نہیں چل|نہیں آ|\b(nahi|nahin)\s+(chal|aa)',
        q
    ):
        return 'support','operational_issue'
    if re.search(
        r'\b(configur(?:e|ation)|set up|setup|new company|opening balances?|account mapping)\b|ترتیب|سیٹ اپ|نئی کمپنی',
        q
    ):
        return 'implementation','configuration'
    if expert in TEAMS:
        return expert,'expert_context'
    return None,'choose_team'

class Contact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    department:Literal['support','implementation']
    name:str=Field(min_length=1,max_length=60)
    phone:str

    @field_validator('phone')
    @classmethod
    def international_phone(cls,value):
        if not isinstance(value,str):
            raise ValueError('Use an international phone number')
        value=re.sub(r'[\s()+-]','',value)
        if value.startswith('00'):
            value=value[2:]
        if not re.fullmatch(r'[1-9][0-9]{7,14}',value):
            raise ValueError('Include the country code, for example 923XXXXXXXXX')
        return value

class Contacts(BaseModel):
    model_config=ConfigDict(extra='forbid')
    company_id:str=Field(min_length=1,max_length=64)
    installation_id:str=Field(min_length=1,max_length=64)
    contacts:list[Contact]=Field(default_factory=list,max_length=20)

    @model_validator(mode='after')
    def unique_contacts(self):
        if len({c.id for c in self.contacts})!=len(self.contacts):
            raise ValueError('Duplicate contact IDs')
        pairs=[(c.department,c.phone) for c in self.contacts]
        if len(set(pairs))!=len(pairs):
            raise ValueError('Duplicate team phone numbers')
        return self

def contacts_path():
    configured=os.environ.get('SPIA_ESCALATION_CONTACTS_FILE')
    if configured:
        return Path(configured).expanduser().resolve()
    return h.database_path().parent/'whatsapp_contacts.json'

def load_contacts(context):
    support=os.environ.get('SPIA_WHATSAPP_SUPPORT')
    implementation=os.environ.get('SPIA_WHATSAPP_IMPLEMENTATION')
    if support is not None or implementation is not None:
        entries=[]
        for team,raw in (('support',support),('implementation',implementation)):
            phones=filter(None,(p.strip() for p in (raw or '').split(',')))
            for number,phone in enumerate(phones,1):
                entries.append({
                    'id':f'{team}-{number}',
                    'department':team,
                    'name':team.title()+f' {number}',
                    'phone':phone,
                })
        data=Contacts(
            company_id=context.identity.company_id,
            installation_id=context.identity.installation_id,
            contacts=entries,
        )
        return data.contacts
    path=contacts_path()
    if not path.is_file():
        return []
    try:
        with path.open('rb') as stream:
            raw=stream.read(32769)
        if len(raw)>32768:
            raise ValueError('Contacts file too large')
        data=Contacts.model_validate_json(raw)
        if (data.company_id,data.installation_id)!=(
            context.identity.company_id,context.identity.installation_id
        ):
            raise ValueError('Contacts belong to another installation')
        return data.contacts
    except (ValueError,OSError,UnicodeError) as exc:
        raise ValueError('WhatsApp contacts need administrator configuration.') from exc

def message(question,module,team,reference,urdu=False,has_image=False):
    label='Support' if team=='support' else 'Implementation'
    if urdu:
        text=(
            f'SPIA اسسٹنٹ — {label}\nماڈیول: {module}\n\nسوال: {question}'
            f'\n\nاسسٹنٹ سے اس سوال کا مکمل مستند جواب نہیں ملا۔ براہ کرم رہنمائی کریں۔'
            f'\nحوالہ: {reference}'
        )
        if has_image:
            text+='\nاس سوال کے ساتھ اسکرین شاٹ تھا۔ میں اسے واٹس ایپ میں الگ سے منسلک کر سکتا ہوں۔'
    else:
        text=(
            f'SPIA Assistant — {label}\nModule: {module}\n\nQuestion: {question}'
            '\n\nThe assistant could not provide a complete documented answer. Please help.'
            f'\nReference: {reference}'
        )
        if has_image:
            text+='\nA screenshot was attached in the assistant. I can attach it separately in WhatsApp.'
    return text

def whatsapp_url(phone,text):
    return 'https://wa.me/'+phone+'?text='+quote(text,safe='')


def live_escalation_proof(answer_proof):
    import hashlib
    import hmac
    secret=(
        os.environ.get('SPIA_RESPONSE_SIGNING_SECRET')
        or os.environ.get('PRESENTER_SESSION_SECRET','')
    )
    if len(secret)<32:
        raise ValueError('Response signing is not configured')
    return hmac.new(
        secret.encode('utf-8'),
        ('SPIA-live-escalation-v1:'+answer_proof).encode('ascii'),
        hashlib.sha256,
    ).hexdigest()
