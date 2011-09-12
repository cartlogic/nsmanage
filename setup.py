from setuptools import setup


setup(name="nsmanage",
      version='0.1',
      description="Manage your hosted DNS configs in python modules.",
      long_description='',
      classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
      ],
      keywords='dns domains cloud softlayer nameservers',
      author='Scott Torborg',
      author_email='scott@cartlogic.com',
      url='http://github.com/cartlogic/nsmanage',
      install_requires=[
          'SoftLayer',
      ],
      dependency_links=[
          'http://github.com/softlayer/softlayer-api-python-client/'
          'tarball/master#egg=SoftLayer',
      ],
      license='MIT',
      packages=['nsmanage'],
      entry_points=dict(console_scripts=['nsmanage=nsmanage:main']),
      test_suite='nose.collector',
      tests_require=['nose'],
      zip_safe=False)
