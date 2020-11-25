from pydantic import BaseModel, HttpUrl
from typing import List
from datetime import datetime, timedelta


class Post(BaseModel):
	html: str
	short_text: str
	full_text: str = None
	parse_datetime: datetime = datetime.now()
	metadata: dict
		
	@property
	def post_datetime(self):
		return datetime.fromtimestamp(int(self.metadata['view_time']))
		
	@property
	def id(self):
		return self.metadata.get('top_level_post_id')
		
	def __str__(self):
		return self.short_text
		
	def __eq__(self, other):
		return self.id == other.id
		

class Posts(BaseModel):
	__root__: List[Post]
	
	def __init__(self, __root__=[]):
		super().__init__(__root__=__root__)
		
	def __getitem__(self, index):
		return self.__root__[index]

	def __iter__(self):
		return iter(self.__root__)
		
	def __len__(self):
		return len(self.__root__)
		
	def __lshift__(self, other):
		self.__root__.append(other)
		
	def __repr__(self):
		return f"Posts({len(self.__root__)} posts)"
		
		
class Config(BaseModel):
	posts: Posts = Posts()
	wait_before_next_update: int = 5 # minutes
	last_update_datetime: datetime = datetime.now() - timedelta(seconds=wait_before_next_update*60+1)
	update_every: int = 60 # minutes
	link_text: str = 'link'
