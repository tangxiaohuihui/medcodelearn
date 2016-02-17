from reader.sparsehierarchical.drgreader import DRGReader
import csv   
import numpy as np      
from vectorize import unitvec


class FlatVectorizedPCReader(DRGReader):
    def read_from_file(self, vectors_by_code, 
                       code_type = 'pdx', 
                       drg_out_file = None,
                       demo_variables_to_use= ['admWeight', 'hmv', 'sex', 'los', 'ageYears', 'ageDays']):
        # available demographic variables:
        # 'id', 'ageYears', 'ageDays', 'admWeight', 'sex', 'adm', 'sep', 'los', 'sdf', 'hmv'
        self.demo_variables_to_use = demo_variables_to_use
        self.code_type = code_type
        self.vectors_by_code = vectors_by_code
        self.invalid_pdx = 0
        self.drg_out_file = drg_out_file
        self.vector_size = len(vectors_by_code[list(vectors_by_code.keys())[0]][0]) + len(self.demo_variables_to_use)
        self.word2vec_dims = self.vector_size - len(self.demo_variables_to_use)
        
        if self.code_type == 'drg':
            if self.drg_out_file == None:
                raise ValueError('You must specify a corresponding DRG output file for the "drg" classification task')
            self.drg_by_id = self.read_drg_output()
        
        dataset = []
        with open(self.filename, 'r') as csvFile:
            reader = csv.DictReader(csvFile, fieldnames=self.FIELDNAMES, restkey=self.RESTKEY, delimiter=';')
            for row in reader:
                for instance in self.get_drg_instances_from_row(row):
                    dataset.append(instance)
                    
        self.data = np.empty((len(dataset), self.vector_size), dtype=np.float32)
        self.targets = []
        
        for i, instance in enumerate(dataset):
            self.data[i] = instance[0]
            self.targets.append(instance[1])
            #print(self.targets[i])
        
        print('Skipped patient cases due to invalid PDX: ' + str(self.invalid_pdx))
        return {'data' : self.data, 'targets' : self.targets}          
    
    def get_drg_instances_from_row(self, row):
        diagproc = row[self.RESTKEY]
        diags = diagproc[0:self.MAX_ADDITIONAL_DIAGNOSES]
        procs = map(lambda x: x.split(':')[0], diagproc[self.MAX_ADDITIONAL_DIAGNOSES:self.MAX_ADDITIONAL_DIAGNOSES+self.MAX_PROCEDURES])
        diags = [d for d in diags if d != '']
        procs = [p for p in procs if p != '']
        diags = map(lambda c: c.replace('.', '').upper(), diags)
        procs = map(lambda c: c.replace('.', '').upper(), procs)
        diags = [d for d in diags if 'ICD_' + d in self.vectors_by_code]
        procs = [p for p in procs if 'CHOP_' + p in self.vectors_by_code]
        pdx = row['pdx'].replace('.', '')
        # do not use this patient case if the PDX is non existent or invalid
        if pdx == '' or 'ICD_' + pdx not in self.vectors_by_code:
            self.invalid_pdx += 1
            return []
             
        
        if self.code_type == 'pdx':
            return [self.flat_instance(row, diags, procs, pdx)]
        elif self.code_type == 'sdx':
            return [self.flat_instance(row, [diag for diag in diags if diag != gt] + [pdx], procs, gt) for gt in diags]
        elif self.code_type == 'srg':
            return [self.flat_instance(row, diags + [pdx], [proc for proc in procs if proc != gt], gt) for gt in procs]
        elif self.code_type == 'drg':
            return [self.flat_instance(row, diags + [pdx], procs, self.drg_by_id[row['id']])]

        raise ValueError('code_type should be one of "drg", "pdx", "sdx" or "srg" but was ' + self.code_type)
    
    def flat_instance(self, row, diags, procs, gt):
        data = np.zeros(self.vector_size - len(self.demo_variables_to_use), dtype=np.float32)
        # sum over all vectors (first vector is the code token)
        for diag in diags:
            for t in self.vectors_by_code['ICD_' + diag]:
                data += t
        for proc in procs:
            for t in self.vectors_by_code['CHOP_' + proc]:
                data += t
        data = unitvec(data)
        data.resize(self.vector_size)
        
        for i, var in enumerate(self.demo_variables_to_use):
            data[self.word2vec_dims + i] = self.convert_demographic_variable(row, var)
        
        return [data, gt]
    
    def convert_demographic_variable(self, row, var):
        value = row[var]
        if var == 'sex':
            return 1.0 if value.upper() == 'M' else -1.0
        return float(value)
    
    def read_drg_output(self):
        drg_by_id = {}
        with open(self.drg_out_file, 'r') as csvFile:
            reader = csv.DictReader(csvFile, self.DRG_OUT_FIELDNAMES, delimiter=';')
            for row in reader:
                drg_by_id[row['id']] = row['drg']
        return drg_by_id
    
